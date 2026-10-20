/** Keep provider/API explanations, but never expose parser errors for gateway pages. */
export async function readApiJson<T = Record<string, unknown>>(
  response: Response,
  unavailableMessage: string,
): Promise<T> {
  const body = await response.text();
  let data: unknown;
  try {
    data = body.trim() ? JSON.parse(body) : null;
  } catch {
    throw new Error(unavailableMessage);
  }
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? data.detail
        : undefined;
    throw new Error(
      typeof detail === "string" && detail.trim() ? detail : unavailableMessage,
    );
  }
  if (!data || typeof data !== "object") throw new Error(unavailableMessage);
  return data as T;
}
