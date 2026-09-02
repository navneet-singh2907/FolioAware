export {
  FolioAwareClient,
  FolioAwareClientError,
  type AskOptions,
  type ClientErrorCode,
  type FolioAwareClientOptions,
} from "./client";
export {
  defineFolioAwareElement,
  FOLIO_AWARE_TAG_NAME,
  FolioAwareElement,
} from "./component";
export type { AnswerStatus, AskResponse, Citation, ProblemResponse } from "./contracts";
export { createEphemeralSessionId, type RandomSource } from "./session";
export { buildAskUrl, isSafeCitationUrl } from "./url-policy";

import { defineFolioAwareElement } from "./component";

defineFolioAwareElement();
