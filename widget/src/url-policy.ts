const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

function containsControlCharacter(value: string): boolean {
  return Array.from(value).some((character) => (character.codePointAt(0) ?? 0) < 32);
}

export function buildAskUrl(apiBaseUrl: string): URL {
  if (apiBaseUrl.trim() !== apiBaseUrl || apiBaseUrl.includes("*")) {
    throw new TypeError("API base URL must be an explicit origin");
  }

  let parsed: URL;
  try {
    parsed = new URL(apiBaseUrl);
  } catch (error) {
    throw new TypeError("API base URL must be absolute", { cause: error });
  }

  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.pathname !== "/" ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new TypeError("API base URL must contain only scheme, host, and port");
  }

  if (parsed.protocol === "http:" && !LOOPBACK_HOSTS.has(parsed.hostname)) {
    throw new TypeError("HTTP API base URLs are limited to loopback development");
  }

  return new URL("/v1/ask", parsed);
}

export function isSafeCitationUrl(value: string): boolean {
  if (
    value.length === 0 ||
    value.trim() !== value ||
    value.includes("\\") ||
    containsControlCharacter(value)
  ) {
    return false;
  }

  if (value.startsWith("/") && !value.startsWith("//")) {
    return true;
  }

  try {
    const parsed = new URL(value);
    return (
      parsed.protocol === "https:" && parsed.username === "" && parsed.password === ""
    );
  } catch {
    return false;
  }
}
