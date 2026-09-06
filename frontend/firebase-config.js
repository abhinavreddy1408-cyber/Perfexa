/**
 * Perfexa Firebase Integration Module.
 * Provides Firebase Authentication, Cloud Firestore synchronization,
 * and hybrid API endpoint routing.
 */

const FIREBASE_CONFIG = {
  projectId: "studio-2619661644-61476",
  appId: "1:363066294094:web:9add11b3bb3693c007281f",
  storageBucket: "studio-2619661644-61476.firebasestorage.app",
  apiKey: "AIzaSyC-e-LHFXdYu3RQTBasoWhHyUbkXWJSw8A",
  authDomain: "studio-2619661644-61476.firebaseapp.com",
  messagingSenderId: "363066294094",
  projectNumber: "363066294094"
};

// Initialize Firebase App
let firebaseApp = null;
let firebaseAuth = null;
let firestoreDb = null;

try {
  if (typeof firebase !== "undefined") {
    if (!firebase.apps.length) {
      firebaseApp = firebase.initializeApp(FIREBASE_CONFIG);
    } else {
      firebaseApp = firebase.app();
    }
    firebaseAuth = firebase.auth();
    firestoreDb = firebase.firestore();
    console.log("[Perfexa Firebase] Initialized successfully. Project:", FIREBASE_CONFIG.projectId);
  } else {
    console.warn("[Perfexa Firebase] Firebase SDK scripts not loaded yet.");
  }
} catch (err) {
  console.error("[Perfexa Firebase] Initialization error:", err);
}

// ---------------------------------------------------------------------------
// Backend Endpoint Management (Hybrid Deployment Support)
// ---------------------------------------------------------------------------
const DEFAULT_LOCAL_BACKEND = "http://127.0.0.1:8000";

function getApiBaseUrl() {
  const savedUrl = localStorage.getItem("perfexa_backend_api_url");
  if (savedUrl && savedUrl.trim()) {
    return savedUrl.trim().replace(/\/+$/, "");
  }

  // If running locally on backend server, use relative path (current origin)
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    return window.location.origin;
  }

  // If running on Firebase Hosting (*.web.app or *.firebaseapp.com),
  // route load generation requests to the local/target backend
  return DEFAULT_LOCAL_BACKEND;
}

function setApiBaseUrl(url) {
  if (!url || !url.trim()) {
    localStorage.removeItem("perfexa_backend_api_url");
  } else {
    localStorage.setItem("perfexa_backend_api_url", url.trim().replace(/\/+$/, ""));
  }
}

async function checkBackendHealth(candidateUrl) {
  const base = candidateUrl || getApiBaseUrl();
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);
    const res = await fetch(`${base}/health`, { signal: controller.signal });
    clearTimeout(timeoutId);
    if (res.ok) {
      const data = await res.json();
      return { ok: true, data };
    }
    return { ok: false, error: `HTTP ${res.status}` };
  } catch (err) {
    return { ok: false, error: err.message || "Connection refused" };
  }
}

// ---------------------------------------------------------------------------
// Authentication Helpers
// ---------------------------------------------------------------------------
async function signUpWithEmail(email, password, displayName) {
  if (!firebaseAuth) throw new Error("Firebase Auth is not initialized.");
  const userCred = await firebaseAuth.createUserWithEmailAndPassword(email, password);
  if (displayName && userCred.user) {
    await userCred.user.updateProfile({ displayName });
  }
  // Record user profile in Firestore
  if (firestoreDb && userCred.user) {
    await firestoreDb.collection("users").doc(userCred.user.uid).set({
      uid: userCred.user.uid,
      email: userCred.user.email,
      displayName: displayName || userCred.user.email.split("@")[0],
      createdAt: firebase.firestore.FieldValue.serverTimestamp(),
      lastLoginAt: firebase.firestore.FieldValue.serverTimestamp()
    }, { merge: true });
  }
  return userCred.user;
}

async function signInWithEmail(email, password) {
  if (!firebaseAuth) throw new Error("Firebase Auth is not initialized.");
  const userCred = await firebaseAuth.signInWithEmailAndPassword(email, password);
  if (firestoreDb && userCred.user) {
    await firestoreDb.collection("users").doc(userCred.user.uid).set({
      lastLoginAt: firebase.firestore.FieldValue.serverTimestamp()
    }, { merge: true });
  }
  return userCred.user;
}

async function signInWithGoogle() {
  if (!firebaseAuth) throw new Error("Firebase Auth is not initialized.");
  const provider = new firebase.auth.GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  const userCred = await firebaseAuth.signInWithPopup(provider);
  if (firestoreDb && userCred.user) {
    await firestoreDb.collection("users").doc(userCred.user.uid).set({
      uid: userCred.user.uid,
      email: userCred.user.email,
      displayName: userCred.user.displayName || userCred.user.email.split("@")[0],
      photoURL: userCred.user.photoURL || null,
      lastLoginAt: firebase.firestore.FieldValue.serverTimestamp()
    }, { merge: true });
  }
  return userCred.user;
}

async function signInAnonymously() {
  if (!firebaseAuth) throw new Error("Firebase Auth is not initialized.");
  const userCred = await firebaseAuth.signInAnonymously();
  return userCred.user;
}

async function signOutUser() {
  if (!firebaseAuth) throw new Error("Firebase Auth is not initialized.");
  await firebaseAuth.signOut();
}

function onAuthChange(callback) {
  if (!firebaseAuth) {
    callback(null);
    return () => {};
  }
  return firebaseAuth.onAuthStateChanged(callback);
}

function getCurrentUser() {
  return firebaseAuth ? firebaseAuth.currentUser : null;
}

// ---------------------------------------------------------------------------
// Cloud Firestore Data Persistence
// ---------------------------------------------------------------------------
async function saveRunToFirestore(runData) {
  if (!firestoreDb) return null;
  const user = getCurrentUser();
  const userId = user ? user.uid : "guest_anonymous";
  const runId = runData.id || `run_${Date.now()}`;

  const payload = {
    id: runId,
    userId: userId,
    userEmail: user ? user.email : "guest",
    prompt: runData.prompt || "",
    test_type: runData.test_type || "baseline",
    status: runData.status || "PENDING",
    target_url: runData.target_url || "",
    virtual_users: runData.virtual_users || 10,
    duration: runData.duration || "30s",
    intent: runData.intent || null,
    synthetic_payloads: runData.synthetic_payloads || null,
    script: runData.script || null,
    metrics: runData.metrics || null,
    ai_report: runData.ai_report || null,
    error_message: runData.error_message || null,
    duration_seconds: runData.duration_seconds || null,
    created_at: runData.created_at || (Date.now() / 1000),
    completed_at: runData.completed_at || null,
    updatedAt: firebase.firestore.FieldValue.serverTimestamp()
  };

  try {
    // If logged in, save to user's private collection
    if (user) {
      await firestoreDb.collection("users").doc(user.uid).collection("runs").doc(runId).set(payload, { merge: true });
      // Also save to top-level runs collection
      await firestoreDb.collection("runs").doc(runId).set(payload, { merge: true });
    }
    console.log(`[Perfexa Firestore] Successfully persisted run ${runId}`);
    return runId;
  } catch (err) {
    console.warn(`[Perfexa Firestore] Note: Cloud save skipped or restricted by rule:`, err.message);
    return null;
  }
}

async function fetchUserRunsFromFirestore(uid) {
  if (!firestoreDb) return [];
  const targetUid = uid || (getCurrentUser() ? getCurrentUser().uid : null);
  if (!targetUid) return [];

  try {
    const snapshot = await firestoreDb.collection("users")
      .doc(targetUid)
      .collection("runs")
      .orderBy("created_at", "desc")
      .limit(50)
      .get();

    const runs = [];
    snapshot.forEach(doc => runs.push(doc.data()));
    return runs;
  } catch (err) {
    console.warn("[Perfexa Firestore] Error loading cloud runs:", err.message);
    return [];
  }
}

// Export to window global namespace for clean consumption
window.PerfexaFirebase = {
  config: FIREBASE_CONFIG,
  getApiBaseUrl,
  setApiBaseUrl,
  checkBackendHealth,
  signUpWithEmail,
  signInWithEmail,
  signInWithGoogle,
  signInAnonymously,
  signOutUser,
  onAuthChange,
  getCurrentUser,
  saveRunToFirestore,
  fetchUserRunsFromFirestore
};
