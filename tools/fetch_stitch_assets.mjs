import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';
import dotenv from 'dotenv';

// Load .env from project root
dotenv.config();

const apiKey = process.env.STITCH_API_KEY;
if (!apiKey) {
  console.error('ERROR: STITCH_API_KEY environment variable is not set in .env or environment.');
  process.exit(1);
}

const PROJECT_ID = '7468309211224946119';
const SCREEN_ID = 'c3118f19be044bd384126371ce74f970';
const ENDPOINT = 'https://stitch.googleapis.com/mcp';

async function fetchScreen() {
  console.log(`Querying Stitch API for Screen ${SCREEN_ID} in Project ${PROJECT_ID}...`);
  
  const payload = {
    jsonrpc: '2.0',
    method: 'tools/call',
    params: {
      name: 'get_screen',
      arguments: {
        projectId: PROJECT_ID,
        screenId: SCREEN_ID,
        name: `projects/${PROJECT_ID}/screens/${SCREEN_ID}`
      }
    },
    id: Date.now()
  };

  const response = await fetch(ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'X-Goog-Api-Key': apiKey
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Stitch API HTTP error ${response.status}: ${errorText}`);
  }

  const result = await response.json();
  if (result.error) {
    throw new Error(`Stitch RPC error: ${JSON.stringify(result.error)}`);
  }

  const screenData = result.result?.structuredContent || result.result;
  console.log('Screen metadata retrieved successfully:');
  console.log(JSON.stringify(screenData, null, 2));

  const outputDir = path.resolve('stitch_assets');
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const htmlUrl = screenData?.htmlCode?.downloadUrl;
  const imageUrl = screenData?.screenshot?.downloadUrl;

  if (htmlUrl) {
    console.log(`\nDownloading HTML from: ${htmlUrl}`);
    const htmlDest = path.join(outputDir, 'perfexa_globe_dark.html');
    execSync(`curl -L "${htmlUrl}" -o "${htmlDest}"`, { stdio: 'inherit' });
    console.log(`Saved HTML to: ${htmlDest}`);
  } else {
    console.warn('No htmlCode.downloadUrl found in response.');
  }

  if (imageUrl) {
    console.log(`\nDownloading Screenshot from: ${imageUrl}`);
    const imageDest = path.join(outputDir, 'perfexa_globe_dark.png');
    execSync(`curl -L "${imageUrl}" -o "${imageDest}"`, { stdio: 'inherit' });
    console.log(`Saved screenshot to: ${imageDest}`);
  } else {
    console.warn('No screenshot.downloadUrl found in response.');
  }
}

fetchScreen().catch(err => {
  console.error('Failed:', err.message);
  process.exit(1);
});
