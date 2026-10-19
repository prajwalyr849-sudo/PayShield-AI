path = r'C:\Users\prajw\OneDrive\Documents\PAYSHIELD-AI\frontend\src\services\api.js'
with open(path) as f:
    s = f.read()
impl = '''export async function parseResponse(response, requestName) {
  const text = await response.text();
  let data = null;
  if (text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      if (response.ok) {
        throw new Error(${requestName} returned malformed JSON.);
      }
    }
  }
  if (!response.ok) {
    const structured =
      data?.detail && typeof data.detail === "object" && !Array.isArray(data.detail)
        ? data.detail
        : null;
    const detail =
      structured?.message ??
      (typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((item) => item.msg).join(", ")
          : typeof data?.reason === "string"
            ? data.reason
            : text.trim() || null);
    const error = new Error(
      detail || ${requestName} failed with status .
    );
    error.status = response.status;
    if (structured?.code) {
      error.code = structured.code;
    }
    if (structured) {
      error.detail = structured;
    }
    throw error;
  }
  if (data === null) {
    throw new Error(${requestName} returned an empty response.);
  }
  return data;
}
'''
s2 = s.rstrip() + '\n\n' + impl
with open(path, 'w') as f:
    f.write(s2)
print('ok')
