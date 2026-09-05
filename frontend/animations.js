/**
 * PerfexaAnimations — GSAP-powered motion design layer for Perfexa frontend.
 *
 * This file is purely additive: it wraps DOM display updates with smooth
 * animations. Removing the <script> tag for this file restores exact
 * previous behavior with zero side effects.
 *
 * Requires: GSAP 3.x loaded before this script.
 */

(function () {
  "use strict";

  // Bail gracefully if GSAP failed to load
  if (typeof gsap === "undefined") {
    console.warn("[PerfexaAnimations] GSAP not found — animations disabled.");
    return;
  }

  // Global defaults: ensure tweens auto-overwrite to prevent backlog
  gsap.defaults({ overwrite: "auto" });

  // =========================================================================
  //  Internal state trackers
  // =========================================================================

  // Tracks proxy objects for stat number tweens so we can kill previous
  const _statProxies = {};

  // Track last known history row count for delta animation
  let _lastHistoryRowCount = 0;

  // =========================================================================
  //  1. PAGE LOAD — Stagger-Fade-In
  // =========================================================================

  function pageLoadEntrance() {
    const tl = gsap.timeline({ defaults: { ease: "power2.out" } });

    const safeFrom = (selector, fromVars, position) => {
      const els = document.querySelectorAll(selector);
      if (els && els.length > 0) {
        tl.from(selector, fromVars, position);
      }
    };

    // Navbar
    safeFrom(".navbar", { y: -20, opacity: 0, duration: 0.5 });

    // Hero section elements
    safeFrom(".hero-badge", { y: 16, opacity: 0, duration: 0.4 }, "-=0.25");
    safeFrom(".hero-title", { y: 16, opacity: 0, duration: 0.45 }, "-=0.2");
    safeFrom(".hero-subtitle", { y: 16, opacity: 0, duration: 0.4 }, "-=0.2");

    // Pipeline cards staggered
    safeFrom(".pipeline-card", { y: 16, opacity: 0, duration: 0.4, stagger: 0.08 }, "-=0.15");

    // Input section card
    safeFrom(".input-section", { y: 16, opacity: 0, duration: 0.4 }, "-=0.15");

    // Preset label and chips
    safeFrom(".preset-label, .chip", { y: 10, opacity: 0, duration: 0.3, stagger: 0.06 }, "-=0.15");

    // Benchmark shortcuts
    safeFrom(".benchmark-shortcuts", { y: 10, opacity: 0, duration: 0.3 }, "-=0.1");
  }

  // =========================================================================
  //  2. INTENT ANALYSIS REVEAL — Scale+Fade
  // =========================================================================

  function revealIntentCard() {
    const section = document.getElementById("intent-section");
    if (!section) return;

    // Kill any existing tweens on this section
    gsap.killTweensOf(section);
    gsap.killTweensOf(section.querySelectorAll("*"));

    // Main card entrance
    gsap.fromTo(
      section,
      { autoAlpha: 0, scale: 0.96, y: 20 },
      {
        autoAlpha: 1,
        scale: 1,
        y: 0,
        duration: 0.45,
        ease: "power2.out",
        clearProps: "scale",
      }
    );

    // Stagger internal children
    const children = section.querySelectorAll(
      ".badge, .tag-item, .criteria-box, .assumptions-list li, .code-preview, .btn-success"
    );
    if (children.length > 0) {
      gsap.fromTo(
        children,
        { autoAlpha: 0, y: 10 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.3,
          stagger: 0.04,
          ease: "power2.out",
          delay: 0.15,
        }
      );
    }
  }

  // =========================================================================
  //  3. LIVE DASHBOARD NUMBERS — Counting Tween
  // =========================================================================

  /**
   * Smoothly tweens a stat element's displayed number from its current
   * value to the new value. Kills any in-flight tween and immediately
   * sets the final value on kill to guarantee correctness.
   *
   * @param {string} elementId - DOM element ID (e.g. "stat-vus")
   * @param {number} newValue  - Target numeric value
   * @param {object} opts      - { suffix: "ms"|"%"|"", decimals: 0|1|2, prefix: "" }
   */
  function tweenStatValue(elementId, newValue, opts = {}) {
    const el = document.getElementById(elementId);
    if (!el) return;

    const suffix = opts.suffix || "";
    const prefix = opts.prefix || "";
    const decimals = opts.decimals !== undefined ? opts.decimals : 0;

    // Parse current displayed value to a number
    const currentText = el.textContent || "0";
    const currentValue = parseFloat(currentText.replace(/[^0-9.\-]/g, "")) || 0;

    // Kill any previous tween on this proxy
    if (_statProxies[elementId]) {
      gsap.killTweensOf(_statProxies[elementId]);
    }

    // Create a fresh proxy object
    const proxy = { val: currentValue };
    _statProxies[elementId] = proxy;

    // If the value hasn't changed, skip
    if (Math.abs(currentValue - newValue) < 0.001) return;

    gsap.to(proxy, {
      val: newValue,
      duration: 0.25,
      ease: "power1.out",
      overwrite: true,
      onUpdate: function () {
        if (decimals === 0) {
          el.textContent = prefix + Math.round(proxy.val) + suffix;
        } else {
          el.textContent = prefix + proxy.val.toFixed(decimals) + suffix;
        }
      },
      onComplete: function () {
        // Guarantee final value is exact (no floating point artifacts)
        if (decimals === 0) {
          el.textContent = prefix + Math.round(newValue) + suffix;
        } else {
          el.textContent = prefix + newValue.toFixed(decimals) + suffix;
        }
      },
    });
  }

  // =========================================================================
  //  4. VERDICT BANNER ENTRANCE — State-Specific Motion
  // =========================================================================

  function animateVerdictBanner(bannerEl) {
    if (!bannerEl) return;

    gsap.killTweensOf(bannerEl);

    const isPassed = bannerEl.classList.contains("verdict-pass");
    const text = (bannerEl.textContent || "").toUpperCase();
    const isPipelineError = text.includes("PIPELINE ERROR");

    if (isPassed) {
      // Confident slide-in from left with slight overshoot
      gsap.fromTo(
        bannerEl,
        { x: -40, autoAlpha: 0 },
        {
          x: 0,
          autoAlpha: 1,
          duration: 0.55,
          ease: "back.out(1.4)",
          clearProps: "x",
        }
      );
    } else if (isPipelineError) {
      // Fade in then shake (slower shake for pipeline error)
      gsap.fromTo(
        bannerEl,
        { autoAlpha: 0, y: -10 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.3,
          ease: "power2.out",
          onComplete: function () {
            gsap.to(bannerEl, {
              keyframes: [
                { x: -8, duration: 0.06 },
                { x: 8, duration: 0.06 },
                { x: -5, duration: 0.06 },
                { x: 4, duration: 0.06 },
                { x: -2, duration: 0.05 },
                { x: 0, duration: 0.05 },
              ],
              ease: "power1.inOut",
              clearProps: "x",
            });
          },
        }
      );
    } else {
      // FAILED / THRESHOLDS BREACHED: sharp shake-then-settle
      gsap.fromTo(
        bannerEl,
        { autoAlpha: 0, y: -10 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.25,
          ease: "power2.out",
          onComplete: function () {
            gsap.to(bannerEl, {
              keyframes: [
                { x: -12, duration: 0.05 },
                { x: 12, duration: 0.05 },
                { x: -8, duration: 0.05 },
                { x: 6, duration: 0.05 },
                { x: -3, duration: 0.04 },
                { x: 0, duration: 0.04 },
              ],
              ease: "power1.inOut",
              clearProps: "x",
            });
          },
        }
      );
    }
  }

  // =========================================================================
  //  5. HISTORY LIST INSERTS — Slide/Fade In
  // =========================================================================

  function animateHistoryRows() {
    const tbody = document.getElementById("history-table-body");
    if (!tbody) return;

    const rows = tbody.querySelectorAll("tr");
    const currentCount = rows.length;

    // Determine which rows are new (delta from last known)
    const newRows = [];
    if (currentCount > _lastHistoryRowCount) {
      const newCount = currentCount - _lastHistoryRowCount;
      for (let i = 0; i < Math.min(newCount, rows.length); i++) {
        newRows.push(rows[i]);
      }
    } else if (_lastHistoryRowCount === 0 && currentCount > 0) {
      // First load — animate all rows
      rows.forEach((r) => newRows.push(r));
    }

    _lastHistoryRowCount = currentCount;

    if (newRows.length > 0) {
      gsap.fromTo(
        newRows,
        { autoAlpha: 0, y: 12 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.3,
          stagger: 0.04,
          ease: "power2.out",
          clearProps: "y",
        }
      );
    }
  }

  // =========================================================================
  //  6. CHART CONTAINER PULSE — Subtle Live Feedback
  // =========================================================================

  // Throttle: don't fire more often than every 800ms
  let _lastChartPulse = 0;

  function pulseChartContainer() {
    const now = Date.now();
    if (now - _lastChartPulse < 800) return;
    _lastChartPulse = now;

    const containers = document.querySelectorAll(".chart-container");
    containers.forEach((container) => {
      gsap.killTweensOf(container, "boxShadow");
      gsap.fromTo(
        container,
        { boxShadow: "0 0 0 1px rgba(255, 255, 255, 0.0)" },
        {
          boxShadow: "0 0 12px 2px rgba(255, 255, 255, 0.08)",
          duration: 0.15,
          ease: "power1.in",
          yoyo: true,
          repeat: 1,
          clearProps: "boxShadow",
        }
      );
    });
  }

  // =========================================================================
  //  7. LIVE DASHBOARD SECTION ENTRANCE
  // =========================================================================

  function revealLiveDashboard() {
    const section = document.getElementById("live-dashboard-section");
    if (!section) return;

    gsap.killTweensOf(section);
    gsap.fromTo(
      section,
      { autoAlpha: 0, y: 20 },
      {
        autoAlpha: 1,
        y: 0,
        duration: 0.45,
        ease: "power2.out",
      }
    );

    // Stagger the stat cards
    const cards = section.querySelectorAll(".stat-card");
    if (cards.length > 0) {
      gsap.fromTo(
        cards,
        { autoAlpha: 0, y: 12 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.3,
          stagger: 0.06,
          ease: "power2.out",
          delay: 0.15,
        }
      );
    }
  }

  // =========================================================================
  //  8. RESULTS SECTION ENTRANCE
  // =========================================================================

  function revealResultsSection() {
    const section = document.getElementById("results-section");
    if (!section) return;

    gsap.killTweensOf(section);
    gsap.fromTo(
      section,
      { autoAlpha: 0, y: 20 },
      {
        autoAlpha: 1,
        y: 0,
        duration: 0.45,
        ease: "power2.out",
      }
    );

    // Stagger the scorecards
    const scorecards = section.querySelectorAll(".stat-card");
    if (scorecards.length > 0) {
      gsap.fromTo(
        scorecards,
        { autoAlpha: 0, y: 10, scale: 0.97 },
        {
          autoAlpha: 1,
          y: 0,
          scale: 1,
          duration: 0.3,
          stagger: 0.05,
          ease: "power2.out",
          delay: 0.2,
          clearProps: "scale",
        }
      );
    }

    // AI report card
    const reportCard = section.querySelector(".ai-report-card");
    if (reportCard) {
      gsap.fromTo(
        reportCard,
        { autoAlpha: 0, y: 15 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.4,
          ease: "power2.out",
          delay: 0.35,
        }
      );
    }
  }

  // =========================================================================
  //  INITIALIZE — Run page load animation on DOMContentLoaded
  // =========================================================================

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", pageLoadEntrance);
  } else {
    requestAnimationFrame(pageLoadEntrance);
  }

  // =========================================================================
  //  PUBLIC API — Exposed on window.PerfexaAnimations
  // =========================================================================

  window.PerfexaAnimations = {
    pageLoadEntrance,
    revealIntentCard,
    tweenStatValue,
    animateVerdictBanner,
    animateHistoryRows,
    pulseChartContainer,
    revealLiveDashboard,
    revealResultsSection,
  };
})();
