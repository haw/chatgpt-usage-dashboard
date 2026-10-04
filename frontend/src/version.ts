// Injected by vite.config.ts: the semantic version in package.json, plus "+<first 8 characters of
// the deployed revision>" when the build knows its commit (APP_REVISION), e.g. 1.0.0+6095c825.
declare const __APP_VERSION__: string

export const CLIENT_VERSION: string = __APP_VERSION__
