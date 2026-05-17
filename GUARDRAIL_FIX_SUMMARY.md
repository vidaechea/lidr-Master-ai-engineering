# Guardrails Error Display Fix - Summary

## 🐛 Bug Report
Los errores derivados de los guardrails (como detección de IBAN) no se mostraban en el frontend cuando se usaba streaming. El texto con IBAN se enviaba al LLM en lugar de ser bloqueado.

## ✅ Root Causes Identified & Fixed

### Issue 1: Backend - Guardrails validated INSIDE streaming generator
**Problem**: The `check_input()` call happened inside the `generate()` async generator, meaning by the time the exception was raised, the HTTP response had already started (HTTP 200).

**File**: `estimator-cag/app/routers/estimations.py`
```python
# BEFORE: Exception caught inside generator after streaming started
async def generate():
    try:
        async for delta in service.estimate_stream(...):
            yield delta
    except InputGuardrailViolation as exc:  # ❌ Too late - response already started!
        raise HTTPException(...)

# AFTER: Validation happens BEFORE streaming starts
try:
    await asyncio.to_thread(check_input, ...)  # ✓ Exception caught before response
except InputGuardrailViolation as exc:
    raise HTTPException(...)  # ✓ Proper HTTP error

async def generate():
    # No guardrai exceptions here
    async for delta in service.estimate_stream(...):
        yield delta
```

### Issue 2: Frontend - Error response parsing
**Problem**: The streaming service converted error responses to plain text, losing the structured error with `reason` field.

**File**: `frontend/src/app/features/estimations/estimation.service.ts`
```typescript
// BEFORE: Lost JSON structure
if (!response.ok) {
    const error = await response.text();
    subscriber.error(new Error(`HTTP ${response.status}: ${error}`)); // ❌ Plain text
}

// AFTER: Parse JSON and extract reason
if (!response.ok) {
    let error = await response.text();
    try {
        const jsonError = JSON.parse(error);
        if (jsonError.detail?.reason) {
            subscriber.error({  // ✓ Structured error
                status: response.status,
                detail: jsonError.detail,
            });
        }
    } catch { /* fallback */ }
}
```

### Issue 3: Frontend - Error handler not recognizing guardrail errors
**Problem**: The error handler only recognized HTTP 400/422 status codes from `HttpErrorResponse`, not from streaming service.

**File**: `frontend/src/app/features/estimations/estimation-form.component.ts`
```typescript
// BEFORE: Only handled HttpErrorResponse
private _handleError(err: HttpErrorResponse) {
    const detail = err.error?.detail;  // Only works with HttpErrorResponse
}

// AFTER: Handles multiple error types
private _handleError(err: unknown) {
    let detail: any = null;
    let status: number | null = null;

    // Handle structured error from streaming
    if (err && typeof err === 'object' && 'status' in err && 'detail' in err) {
        status = (err as any).status;
        detail = (err as any).detail;
    }
    // Handle HttpErrorResponse
    else if (err instanceof HttpErrorResponse) {
        status = err.status;
        detail = err.error?.detail;
    }
    
    // Now properly sets guardrailError signal
    if (detail?.reason && (status === 400 || status === 422)) {
        this.guardrailError.set(detail as GuardrailError);
    }
}
```

## 📝 Files Modified

1. **Backend**
   - `estimator-cag/app/routers/estimations.py` - Moved guardrail validation before streaming

2. **Frontend**
   - `frontend/src/app/features/estimations/estimation.service.ts` - Enhanced error parsing
   - `frontend/src/app/features/estimations/estimation-form.component.ts` - Better error handling

## 🧪 Test Case
1. Enter text containing an IBAN (e.g., "ES9121436481936411235814") in the textarea
2. Click "Estimate"
3. **Expected**: Error message shows "IBAN detected in description — please remove personal data"
4. **Before fix**: Request was sent to LLM
5. **After fix**: ✓ Request is blocked with guardrail warning

## ⚙️ Technical Details

### Error Response Format
```json
{
  "detail": {
    "message": "IBAN detected in description — please remove personal data.",
    "reason": "pii"
  }
}
```

### HTTP Status Codes
- `400`: Moderation violations
- `422`: Prompt injection or PII violations

### Guardrail Reasons
- `"pii"` - Personal Identifiable Information (emails, phones, IBANs)
- `"prompt_injection"` - Suspicious instruction-like text
- `"moderation"` - OpenAI Moderation API violations
