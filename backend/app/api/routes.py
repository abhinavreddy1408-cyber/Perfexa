"""
FastAPI Routes for AI-Powered Autonomous Performance Testing Platform.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db, async_session
from backend.app.models import TestRun
from backend.app.schemas.intent import TestIntent, MergedIntentPayloadResponse
from backend.app.services.llm_intent import extract_intent_and_payloads
from backend.app.services.k6_generator import build_and_validate_k6_script
from backend.app.services.k6_runner import execute_k6_run
from backend.app.services.llm_summary import generate_performance_summary
from backend.app.services.docker_utils import get_effective_target_url
from backend.app.services.code_analyzer import analyze_code_content, UnsupportedLanguageError, InvalidFileError
from backend.app.services.llm_code_summary import generate_code_quality_summary
from backend.app.api.websocket import ws_manager

logger = logging.getLogger("routes")
router = APIRouter(prefix="/api")


class IntentRequest(BaseModel):
    prompt: str
    target_url: Optional[str] = None


class StartTestRunRequest(BaseModel):
    prompt: str
    intent: Dict[str, Any]
    synthetic_payloads: Optional[Dict[str, Any]] = None


async def run_load_test_pipeline(run_id: str, prompt: str, intent_dict: Dict[str, Any], payloads_dict: Optional[Dict[str, Any]] = None):
    """
    Background worker executing the complete autonomous test pipeline:
    1. Validates & compiles k6 script
    2. Executes k6 load test, tails live metrics to WebSocket
    3. Analyzes results with LLM post-run summary
    4. Persists final state to SQLite
    """
    logger.info(f"Starting background pipeline for run {run_id}")
    start_time = time.time()
    
    async with async_session() as session:
        # Load run
        result = await session.execute(select(TestRun).where(TestRun.id == run_id))
        run_record = result.scalars().first()
        if not run_record:
            logger.error(f"Run {run_id} not found in DB")
            return

        try:
            # 1. Generate k6 script
            run_record.status = "GENERATING_SCRIPT"
            await session.commit()
            await ws_manager.broadcast_status(run_id, "GENERATING_SCRIPT")

            intent_dict["target_url"] = get_effective_target_url(intent_dict.get("target_url"))
            intent_obj = TestIntent.model_validate(intent_dict)
            payloads = payloads_dict or {}
            merged = MergedIntentPayloadResponse(intent=intent_obj, synthetic_payloads=payloads)

            # Generate script with 2s smoke run and self-healing retry
            script_code, script_path = await asyncio.to_thread(
                build_and_validate_k6_script, merged, run_id
            )

            run_record.script_content = script_code
            run_record.status = "RUNNING"
            await session.commit()
            await ws_manager.broadcast_status(run_id, "RUNNING", {"script": script_code})

            # 2. Execute k6 load test and stream metrics
            async def on_metric_update(snapshot):
                await ws_manager.broadcast_metric(run_id, snapshot)

            final_metrics = await execute_k6_run(
                run_id=run_id,
                script_path=script_path,
                success_criteria=intent_obj.success_criteria,
                on_metric_update=on_metric_update
            )

            run_record.metrics_summary_json = json.dumps(final_metrics)
            run_record.status = "GENERATING_SUMMARY"
            await session.commit()
            await ws_manager.broadcast_status(run_id, "GENERATING_SUMMARY", {"metrics": final_metrics})

            # 3. Generate AI summary
            ai_summary = await asyncio.to_thread(
                generate_performance_summary, intent_obj, final_metrics
            )

            # 4. Finalize run
            end_time = time.time()
            run_record.ai_report = ai_summary
            run_record.status = "COMPLETED"
            run_record.completed_at = end_time
            run_record.duration_seconds = round(end_time - start_time, 2)
            await session.commit()

            await ws_manager.broadcast_status(run_id, "COMPLETED", {
                "metrics": final_metrics,
                "ai_report": ai_summary,
                "duration_seconds": run_record.duration_seconds
            })
            logger.info(f"Pipeline completed successfully for run {run_id}")

        except Exception as e:
            logger.error(f"Pipeline error for run {run_id}: {e}", exc_info=True)
            run_record.status = "FAILED"
            run_record.error_message = str(e)
            run_record.completed_at = time.time()
            run_record.duration_seconds = round(time.time() - start_time, 2)
            await session.commit()
            await ws_manager.broadcast_status(run_id, "FAILED", {"error": str(e)})


@router.post("/intent")
async def extract_intent_endpoint(req: IntentRequest):
    """Extracts test intent and synthetic payloads from natural language."""
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty. Please enter a performance test description.")
    try:
        res = await asyncio.to_thread(extract_intent_and_payloads, req.prompt, req.target_url)
        return res.model_dump()
    except (ValueError, ValidationError) as e:
        logger.warning(f"Validation / intent extraction error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error extracting intent: {e}")
        raise HTTPException(status_code=500, detail=f"Intent extraction failed: {str(e)}")


@router.post("/runs")
async def start_run_endpoint(
    req: StartTestRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Creates a new test run and begins background execution."""
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    intent_data = req.intent

    run_record = TestRun(
        id=run_id,
        prompt=req.prompt,
        test_type=intent_data.get("test_type", "baseline"),
        status="PENDING",
        target_url=get_effective_target_url(intent_data.get("target_url")),
        virtual_users=intent_data.get("virtual_users", 10),
        duration=intent_data.get("duration", "30s"),
        intent_json=json.dumps(intent_data),
        synthetic_payloads_json=json.dumps(req.synthetic_payloads or {}),
        created_at=time.time()
    )

    db.add(run_record)
    await db.commit()

    # Launch background task via asyncio with safety wrapper
    async def _safe_pipeline_wrapper():
        """Wraps the pipeline so any crash (including before the pipeline's own try/except) is caught and the run is marked FAILED."""
        try:
            await run_load_test_pipeline(run_id, req.prompt, intent_data, req.synthetic_payloads)
        except Exception as exc:
            logger.error(f"Unhandled pipeline crash for run {run_id}: {exc}", exc_info=True)
            try:
                async with async_session() as err_session:
                    result = await err_session.execute(select(TestRun).where(TestRun.id == run_id))
                    stuck_run = result.scalars().first()
                    if stuck_run and stuck_run.status not in ("COMPLETED", "FAILED"):
                        stuck_run.status = "FAILED"
                        stuck_run.error_message = f"Pipeline crash: {str(exc)}"
                        stuck_run.completed_at = time.time()
                        await err_session.commit()
                        await ws_manager.broadcast_status(run_id, "FAILED", {"error": str(exc)})
            except Exception as db_err:
                logger.error(f"Could not mark run {run_id} as FAILED in DB: {db_err}")

    asyncio.create_task(_safe_pipeline_wrapper())

    return {
        "run_id": run_id,
        "status": "PENDING",
        "message": "Test execution launched"
    }


@router.get("/runs")
async def list_runs_endpoint(db: AsyncSession = Depends(get_db)):
    """Lists past test runs ordered by creation date descending."""
    result = await db.execute(select(TestRun).order_by(desc(TestRun.created_at)).limit(50))
    runs = result.scalars().all()
    return [r.to_dict() for r in runs]


@router.get("/runs/{run_id}")
async def get_run_endpoint(run_id: str, db: AsyncSession = Depends(get_db)):
    """Gets detailed record of a specific test run."""
    result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return run.to_dict()


@router.get("/runs/{run_id}/metrics")
async def get_run_live_metrics_endpoint(run_id: str):
    """Polling fallback endpoint returning latest live metric snapshot."""
    snapshot = ws_manager.get_latest_metrics(run_id)
    if not snapshot:
        return {"status": "waiting_or_completed", "run_id": run_id}
    return snapshot


@router.post("/code-review")
async def code_review_endpoint(
    file: UploadFile = File(...),
    run_ai_summary: bool = Form(True)
):
    """
    Codebase Corrector endpoint: accepts a single source code file (.py or .js),
    runs static analysis (Flake8 / ESLint), and returns structured findings plus
    a grounded AI quality summary.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    filename = file.filename

    try:
        raw_bytes = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(status_code=400, detail="Could not read uploaded file.")

    if not raw_bytes or not raw_bytes.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Uploaded file contains binary data or invalid text encoding.")

    try:
        analysis_result = await asyncio.to_thread(analyze_code_content, filename, content)
    except UnsupportedLanguageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidFileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Code analysis error for {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Code analysis failed: {str(e)}")

    ai_summary = ""
    if run_ai_summary:
        try:
            ai_summary = await asyncio.to_thread(generate_code_quality_summary, analysis_result)
        except Exception as e:
            logger.error(f"Failed to generate AI code summary for {filename}: {e}", exc_info=True)
            ai_summary = f"Analysis complete with {analysis_result['total_findings']} findings. AI summary generation encountered a temporary error."

    analysis_result["ai_summary"] = ai_summary
    return analysis_result
