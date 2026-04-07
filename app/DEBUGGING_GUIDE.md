# EventSource Streaming Debugging Guide

## Problem Statement

Users report that clicking "Start Processing", "Start Collection Run", or "Start JE Validation" buttons have no effect. No invoices, collections, or journal entries appear in the queue, and users receive no error feedback.

## Root Cause Analysis

The app uses HTML5 **EventSource (Server-Sent Events)** to stream real-time data from the backend:

```javascript
// frontend/src/hooks/useSSE.ts
const es = new EventSource(url);  // e.g., "/stream/p2p"
```

When the button is clicked, `stream.start()` is called, which:
1. Creates a new EventSource connection
2. Sets up onmessage listener for events
3. If connection fails, silently closes without user feedback

**The most likely cause:** The EventSource request to `/stream/p2p` (or `/stream/o2c`, `/stream/r2r`) fails due to:
1. **CORS misconfiguration** - Databricks Apps proxy not forwarding proper headers
2. **Authentication failure** - Missing auth headers on EventSource request
3. **Proxy routing issue** - `/stream/*` endpoints not properly proxied to backend
4. **Silent error handling** - No user-visible error messages

## Code Changes Applied

### 1. Enhanced Error Handling (useSSE.ts)

**What was changed:**
- Added `error` state to track stream failures
- Added try-catch around EventSource creation
- Added detailed error messages to `es.onerror` handler
- Logs errors to browser console with `console.error()`

**Code:**
```javascript
// BEFORE: Silent failure
es.onerror = () => {
  setIsStreaming(false);
  es.close();
};

// AFTER: User-visible error
es.onerror = (err) => {
  console.error("SSE connection error:", err);
  setError(`Stream failed: ${statusText}. Check browser console for details.`);
  setIsStreaming(false);
  es.close();
};
```

### 2. Error Display UI (APTab.tsx, ARTab.tsx, GLTab.tsx)

**What was changed:**
- Added error alert component above the greeting banner
- Displays red error box with AlertTriangle icon
- Shows error message to user with actionable next steps

**Code:**
```jsx
{stream.error && (
  <div className="px-4 py-3 rounded-lg bg-db-red/10 border border-db-red/30 flex items-start gap-3">
    <AlertTriangle className="w-4 h-4 text-db-red flex-shrink-0 mt-0.5" />
    <div className="flex-1">
      <p className="text-sm text-db-red font-medium">Stream Error</p>
      <p className="text-xs text-text-secondary mt-0.5">{stream.error}</p>
    </div>
  </div>
)}
```

## Diagnostics: How to Find the Root Cause

### Step 1: Enable Browser DevTools Console

Open the app in Chrome or Safari:
1. Press **F12** to open Developer Tools
2. Go to **Console** tab
3. Look for any red error messages when you click "Start Processing"

**Expected output on success:**
```
[No errors, stream starts flowing]
```

**Expected output on failure:**
```
SSE connection error: <error details>
```

### Step 2: Check Network Tab for EventSource Request

1. In DevTools, go to **Network** tab
2. Click "Start Processing" button
3. Look for a request to `/stream/p2p`

**If the request EXISTS:**
- Click it to view details
- Check **Status** column:
  - `200 OK` → Server responded but client not receiving (SSE parsing issue)
  - `401 Unauthorized` → Auth failure (headers not injected)
  - `403 Forbidden` → Permission issue
  - `404 Not Found` → Route doesn't exist (proxy routing issue)
  - No response → Connection pending/hanging (timeout)

**If the request DOES NOT EXIST:**
- The hook is not being called
- Check if component is mounted
- Verify URL is being passed correctly

### Step 3: Check Browser Console for Specific Errors

After applying the code changes, you should see one of these errors:

**Case 1: CORS Error**
```
Access to EventSource at 'https://akash-finance-demo-xxx.aws.databricksapps.com/stream/p2p'
has been blocked by CORS policy
```
**Fix:** Configure Databricks Apps proxy to forward proper CORS headers

**Case 2: Authentication Error (401)**
```
SSE connection error: Unauthorized
```
**Fix:** Verify Databricks OAuth headers are being injected by proxy

**Case 3: Timeout**
```
SSE connection error: Connection closed
```
**Fix:** Check backend logs to verify stream endpoint is being called

**Case 4: Network Error (offline, proxy down)**
```
SSE connection error: Failed to fetch
```
**Fix:** Verify backend service is running and reachable

## Files Modified

1. **frontend/src/hooks/useSSE.ts**
   - Added `error` state
   - Added try-catch error handling
   - Added console logging
   - Exported error in return value

2. **frontend/src/components/APTab.tsx**
   - Added error alert UI above GreetingBanner

3. **frontend/src/components/ARTab.tsx**
   - Added error alert UI above GreetingBanner

4. **frontend/src/components/GLTab.tsx**
   - Added error alert UI above GreetingBanner

## Next Steps to Deploy

1. **Test locally first** (if possible):
   ```bash
   cd frontend
   npm run build
   cp -r dist/* ../backend/static/
   cd ../backend
   uvicorn main:app --reload
   # Navigate to http://localhost:8000
   # Click Start Processing and check console
   ```

2. **Deploy to Databricks**:
   - Push changes to repo
   - Trigger app redeploy via Databricks CLI:
     ```bash
     databricks apps deploy
     ```

3. **Verify in production**:
   - Navigate to https://akash-finance-demo-xxx.aws.databricksapps.com
   - Authenticate with Databricks OAuth
   - Click "Start Processing"
   - Check browser console (F12 → Console tab)
   - If error appears, copy error message and check against cases above

## Advanced Debugging: Backend Logs

If the EventSource request never reaches the backend, check Databricks App logs:

```bash
# View app container logs
databricks apps logs <app-id>

# Look for entries like:
# GET /stream/p2p HTTP/1.1
# or
# 404 Not Found for /stream/p2p
```

## Verification Checklist

After deploying the code changes:

- [ ] App builds without errors
- [ ] No console errors during initial load
- [ ] Metric cards load (KPIs visible)
- [ ] "Start Processing" button is clickable
- [ ] After clicking, one of these happens:
  - [ ] Greeting message appears + invoices flow (SUCCESS)
  - [ ] Error message appears in red box (HELPS DIAGNOSE)
  - [ ] Nothing happens (check console for errors)
- [ ] If error appears, error message is descriptive and actionable

## Common Solutions

### If you see "CORS" error:
- Databricks Apps proxy configuration needs SSE support
- May require Databricks support ticket if proxy is misconfigured

### If you see "401" or "403" error:
- Check that x-forwarded-email and x-forwarded-access-token headers are injected by proxy
- May need to add header passthrough configuration

### If you see "404" error:
- Backend route `/stream/p2p` not found
- Verify app.yaml command correctly starts uvicorn server
- Verify no FastAPI middleware is blocking the route

### If you see "Connection closed" with no data:
- Backend service might be crashing
- Check backend logs for exceptions
- Verify database connectivity works

## Long-term Improvements (Future)

1. **Add retry logic** with exponential backoff
   ```javascript
   // Retry failed connections up to 3 times
   const MAX_RETRIES = 3;
   const retryWithBackoff = async (attempt = 0) => {
     try {
       // create EventSource
     } catch (err) {
       if (attempt < MAX_RETRIES) {
         await sleep(1000 * Math.pow(2, attempt));
         retryWithBackoff(attempt + 1);
       }
     }
   };
   ```

2. **Add timeout handling**
   ```javascript
   // Close EventSource if no data for 30 seconds
   const timeoutId = setTimeout(() => {
     if (!gotData) {
       setError("Stream timeout - no data received");
       es.close();
     }
   }, 30000);
   ```

3. **Add reconnection logic for auth token expiry**
   ```javascript
   // If 401 occurs during stream, trigger re-auth
   if (err.status === 401) {
     // Trigger Databricks OAuth refresh
   }
   ```

4. **Add stream health metrics**
   ```javascript
   // Track bytes received, events processed, lag
   const [streamHealth, setStreamHealth] = useState({
     bytesReceived: 0,
     eventsProcessed: 0,
     lastEventTime: 0,
     lag: 0,
   });
   ```

## Support Escalation

If after applying these changes the error persists, collect:

1. **Browser console error message** (screenshot)
2. **Network tab request/response** (Network tab screenshot showing /stream/p2p request)
3. **Backend logs** from Databricks App container
4. **App URL** being tested
5. **User email** authenticating

Then escalate to Databricks support with Databricks Apps proxy configuration question.

