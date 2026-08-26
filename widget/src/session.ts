export interface RandomSource {
  randomUUID?: () => string;
  getRandomValues: Crypto["getRandomValues"];
}

export function createEphemeralSessionId(
  randomSource: RandomSource = globalThis.crypto,
): string {
  if (typeof randomSource.randomUUID === "function") {
    return randomSource.randomUUID();
  }

  const bytes = randomSource.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes.at(6) ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes.at(8) ?? 0) & 0x3f) | 0x80;
  const hexadecimal = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `${hexadecimal.slice(0, 8)}-${hexadecimal.slice(8, 12)}-${hexadecimal.slice(12, 16)}-${hexadecimal.slice(16, 20)}-${hexadecimal.slice(20)}`;
}
