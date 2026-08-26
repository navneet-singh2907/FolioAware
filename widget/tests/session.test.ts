import { describe, expect, it } from "vitest";

import { createEphemeralSessionId, type RandomSource } from "../src/session";

describe("createEphemeralSessionId", () => {
  it("uses the platform random UUID when available", () => {
    const source: RandomSource = {
      randomUUID: () => "platform-random-id",
      getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto),
    };

    expect(createEphemeralSessionId(source)).toBe("platform-random-id");
  });

  it("creates a UUID v4 from cryptographic random bytes as a fallback", () => {
    const source: RandomSource = {
      getRandomValues: ((array: Uint8Array) => {
        array.fill(0);
        return array;
      }) as Crypto["getRandomValues"],
    };

    expect(createEphemeralSessionId(source)).toBe(
      "00000000-0000-4000-8000-000000000000",
    );
  });
});
