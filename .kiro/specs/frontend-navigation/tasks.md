# Implementation Plan: Frontend Navigation Architecture

## Overview

This plan implements the routing, layout, and post-login navigation architecture from `design.md`. Work proceeds bottom-up: pure, property-tested logic modules first (post-login redirect resolution, navbar route matching, onboarding guard decision, id-token email decoding, token extraction, profile-outcome mapping), then the data hooks that consume them, then the `AuthContext`/`CallbackView` contract change, then the new UI shell (`Navbar`/`Layout`/`LandingPage`/`Dashboard`/`NotFoundView`/`OnboardingGuard`), then the `Step1ProfileParse`/`Step2Roles` reuse refactor (with its mandatory manual regression check), then `ProfileView`, and finally the `App.tsx` route-tree rewiring that ties every piece together. This project has no `@testing-library/react`; only pure functions are covered by automated tests (Vitest + `fast-check`), matching the existing convention in `frontend/src/lib/__tests__/`.

## Tasks

- [ ] 1. Implement profile-outcome mapping and the `MeProfile` type
  - [ ] 1.1 Add `MeProfile` type to `frontend/src/api/types.ts` and implement `mapProfileQueryToOutcome` in `frontend/src/api/profileCheck.ts`
    - `GET /me/profile` now has a typed response schema (`ProfileResponse`) in `openapi/openapi.json`, generated from the backend's `backend.shared.models.ProfileResponse` Pydantic model. `MeProfile` is therefore no longer hand-defined: declare it as `export type MeProfile = ProfileResponse;` in `frontend/src/api/types.ts`, reusing the `ProfileResponse` re-export already added in the "--- Profile ---" section (`export type ProfileResponse = components["schemas"]["ProfileResponse"];`), following this file's existing convention of only re-exporting generated types, never hand-defining them
    - Export `ProfileCheckOutcome` (`"loading" | "exists" | "not_found" | "error"` variants) from `profileCheck.ts` per the Data Models section
    - `mapProfileQueryToOutcome` checks `isLoading` first, before reading `data`/`error`/`isError` at all; this part is unchanged by the `MeProfile` type-source change
    - _Requirements: 2.2, 2.3, 2.4, 2.5_
  - [ ]* 1.2 Write unit tests for `mapProfileQueryToOutcome`
    - Example-based (per design's Testing Strategy classification, not property-based): `isLoading: true` → `"loading"`; `data` present → `"exists"`; 404 `error`/`isError` → `"not_found"`; 5xx/network `error`/`isError` → `"error"` with message
    - _Requirements: 2.2, 2.5, 10.1_

- [ ] 2. Implement post-login destination resolution
  - [ ] 2.1 Implement `resolvePostLoginDestination` in `frontend/src/lib/postLoginRedirect.ts`
    - Signature: `resolvePostLoginDestination(profileStatus: "exists" | "not_found", savedRedirect: string | null): string`
    - `"not_found"` → always `"/onboarding/1"` regardless of `savedRedirect`
    - `"exists"` → `savedRedirect` when non-empty string, else `"/"`
    - _Requirements: 2.3, 2.4, 6.2_
  - [ ]* 2.2 Write property test and unit tests for `resolvePostLoginDestination`
    - **Property 1: Post-login destination resolution**
    - **Validates: Requirements 2.3, 2.4, 6.2**
    - Tag: `// Feature: frontend-navigation, Property 1: Post-login destination resolution`
    - Property: generate arbitrary redirect strings (including `null`/empty) crossed with both outcomes, minimum 100 iterations, using `fast-check`
    - Unit examples: `not_found` with a redirect present (ignored), `exists` with `null`/`""` (falls back to `"/"`)

- [ ] 3. Implement navbar route matching
  - [ ] 3.1 Implement `isNavbarRoute` in `frontend/src/lib/navbarRoutes.ts`
    - Signature: `isNavbarRoute(pathname: string): boolean`, using `matchPath` from `react-router-dom` against `["/", "/vacancies", "/vacancies/:companyId/:vacancyId", "/applications", "/applications/:companyId/:vacancyId", "/sources", "/profile"]`
    - _Requirements: 3.2, 3.3, 7.3_
  - [ ]* 3.2 Write property test and unit tests for `isNavbarRoute`
    - **Property 2: Navbar route matching is total and correct**
    - **Validates: Requirements 3.2, 3.3, 7.3**
    - Tag: `// Feature: frontend-navigation, Property 2: Navbar route matching is total and correct`
    - Property: arbitrary non-empty string segments substituted into the two dynamic route templates → `true`; arbitrary `:step` values substituted into `/onboarding/:step`, and the literal `/callback` → `false`. Minimum 100 iterations
    - Unit examples: each static route in the Requirement 3.2 list, plus `/callback` and `/onboarding/3`

- [ ] 4. Implement onboarding guard decision
  - [ ] 4.1 Implement `resolveOnboardingGuardAction` in `frontend/src/lib/onboardingGuard.ts`
    - Signature: `resolveOnboardingGuardAction(profileStatus: "exists" | "not_found"): "redirect_to_profile" | "render"`; deliberately takes no `:step` parameter
    - _Requirements: 5.2_
  - [ ]* 4.2 Write property test and unit tests for `resolveOnboardingGuardAction`
    - **Property 4: Onboarding guard action is independent of the requested step**
    - **Validates: Requirements 5.2**
    - Tag: `// Feature: frontend-navigation, Property 4: Onboarding guard action is independent of the requested step`
    - Property: arbitrary step strings (numeric, non-numeric, empty) crossed with both outcomes; assert the step value never affects the result. Minimum 100 iterations
    - Unit examples: `"exists"` → `"redirect_to_profile"`, `"not_found"` → `"render"`

- [ ] 5. Implement id-token email decoding
  - [ ] 5.1 Implement `decodeIdToken` and `getEmailFromIdToken` in `frontend/src/auth/idTokenClaims.ts`
    - Base64url-decodes the JWT payload segment; returns `null` on malformed input instead of throwing (feeds UI display only, no signature verification needed client-side)
    - _Requirements: 4.6_
  - [ ]* 5.2 Write property test and unit tests for `getEmailFromIdToken`/`decodeIdToken`
    - **Property 3: ID token email round-trip**
    - **Validates: Requirements 4.6**
    - Tag: `// Feature: frontend-navigation, Property 3: ID token email round-trip`
    - Property: generate arbitrary non-empty email strings, build a fake JWT via a small test-only base64url encoder mirroring `pkce.ts`'s `base64UrlEncode`, encode as the `email` claim, decode with `getEmailFromIdToken`, assert exact round-trip. Minimum 100 iterations
    - Unit examples: malformed/undecodable token → `null` (no throw)

- [ ] 6. Implement token extraction from the Cognito token-exchange response
  - [ ] 6.1 Implement `extractTokensFromResponse` and `exchangeCodeForTokens` in `frontend/src/auth/tokenExchange.ts`
    - `extractTokensFromResponse(body: unknown): { accessToken: string; idToken: string }` throws when `access_token`/`id_token` is missing or empty, matching today's `handleCallback` error behavior
    - `exchangeCodeForTokens` wraps the existing `fetch` call to the Cognito token endpoint (moved out of `AuthContext.handleCallback`) and parses the response via `extractTokensFromResponse`
    - _Requirements: 8.1_
  - [ ]* 6.2 Write property test and unit tests for `extractTokensFromResponse`
    - **Property 5: Token extraction round-trip and failure contract**
    - **Validates: Requirements 8.1**
    - Tag: `// Feature: frontend-navigation, Property 5: Token extraction round-trip and failure contract`
    - Property: arbitrary non-empty string pairs for `access_token`/`id_token` → returned exactly as `accessToken`/`idToken`; arbitrary partial/empty-string objects → throws. Minimum 100 iterations
    - Unit examples: missing `id_token`, missing `access_token`, empty-string token (each throws)

- [ ] 7. Checkpoint - Ensure all pure-module tests pass
  - Run `npm run test` in `frontend/`. This is auto-verifiable: if the suite passes, continue automatically to task 8 without asking the user for confirmation. If any test fails, stop and report the failure instead of continuing.

- [ ] 8. Implement profile data query hooks
  - [ ] 8.1 Implement `useProfileData` in `frontend/src/api/queries/useProfileData.ts`
    - Single real query for `GET /me/profile`, keyed with `profileKey()` from `queryKeys.ts`, returns `UseQueryResult<MeProfile>`
    - _Requirements: 4.2, 4.5, 4.6_
  - [ ] 8.2 Implement `useProfileCheckStatus` in `frontend/src/api/queries/useProfileCheckStatus.ts`
    - Thin wrapper: calls `useProfileData()` (same `profileKey()`, no duplicate `queryFn`), passes `{data, error, isError, isLoading}` through `mapProfileQueryToOutcome`
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 5.2_

- [ ] 9. Refactor `AuthContext.handleCallback` to stop navigating internally
  - [ ] 9.1 Rewrite `handleCallback` in `frontend/src/auth/AuthContext.tsx` to delegate to `exchangeCodeForTokens`
    - Remove the trailing `window.location.href = savedRoute` block and the `sessionStorage.removeItem` calls (both move to `CallbackView`)
    - `handleCallback` keeps: read `pkce_code_verifier`, call `exchangeCodeForTokens`, `tokenStore.setTokens`, `setIsAuthenticated(true)`, resolve; unchanged throw/reject behavior on failure
    - _Requirements: 8.1_

- [ ] 10. Refactor `CallbackView` to own post-login navigation
  - [ ] 10.1 Implement the navigation sequence in `frontend/src/screens/auth/CallbackView.tsx`
    - After `await handleCallback(code)` resolves, clear `post_login_redirect` and `pkce_code_verifier` from `sessionStorage` unconditionally, before reading `useProfileCheckStatus()`
    - While `outcome.status === "loading"`, keep rendering the existing "Autenticando..." state
    - On `"error"` → reuse `ErrorState` with `onRetry` re-invoking the query's `refetch()`
    - On `"exists"`/`"not_found"` → call `resolvePostLoginDestination` (or `"/onboarding/1"` directly for `not_found`), then `navigate(destination, { replace: true })`
    - The existing `.catch()` on `handleCallback()` short-circuits before any profile check; `sessionStorage` is NOT cleared on this branch
    - Add a `logStructuredError(event: string, detail: unknown)` helper and use it for all caught errors (`console.error(JSON.stringify({event, ...}))`); never log CV text or profile content
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 6.2, 6.3, 8.2, 8.3, 10.1, 10.2, 10.3, 10.4_

- [ ] 11. Implement `Navbar` and `Layout` components
  - [ ] 11.1 Implement `frontend/src/components/Navbar.tsx`
    - Three sections per Requirement 3.4: left logo link to `/`; center links (`Vacantes`, `Postulaciones`, `Fuentes`) visible only when `isAuthenticated`; right section swaps `Iniciar sesión` vs. `Perfil` + `Cerrar sesión`
    - Mobile disclosure panel below `md` breakpoint using `aria-expanded`/`aria-controls` and Tailwind responsive classes
    - _Requirements: 3.1, 3.4, 9.4_
  - [ ] 11.2 Implement `frontend/src/components/Layout.tsx`
    - Renders `<Navbar />` followed by `<Outlet />`, used only as the `element` of the parent route wrapping the Requirement 3.2 route list
    - _Requirements: 3.5, 3.6_

- [ ] 12. Implement the root route screens
  - [ ] 12.1 Implement `frontend/src/screens/home/LandingPage.tsx`
    - Static marketing copy, platform name/logo, and an "Iniciar sesión" button calling `login()`; responsive on mobile/tablet/desktop
    - _Requirements: 1.2, 1.3, 9.1, 9.2_
  - [ ] 12.2 Implement `frontend/src/screens/home/Dashboard.tsx`
    - Personalized greeting using `getEmailFromIdToken(tokenStore.getIdToken())`, quick-access links to `/vacancies` and `/applications`, no marketing copy; falls back gracefully (omits greeting) when the id token is malformed/undecodable
    - _Requirements: 1.4, 1.5, 9.1, 9.3_
  - [ ] 12.3 Implement `frontend/src/screens/home/RootRoute.tsx`
    - Reads `isAuthenticated` from `useAuth()`, renders `<LandingPage/>` or `<Dashboard/>`
    - _Requirements: 1.1, 1.2, 1.4_

- [ ] 13. Implement the public `NotFoundView`
  - [ ] 13.1 Implement `frontend/src/screens/NotFoundView.tsx`
    - Always renders a "Volver al inicio" link to `/`; if unauthenticated, also renders an "Iniciar sesión" button calling `login()`; if authenticated, renders `<Navbar/>` above the 404 content instead of being unguarded
    - Same Tailwind design system as the rest of the app
    - _Requirements: 7.2_

- [ ] 14. Implement the `OnboardingGuard` screen wrapper
  - [ ] 14.1 Implement `frontend/src/screens/onboarding/OnboardingGuard.tsx`
    - Reads `useProfileCheckStatus()`; `"loading"` → spinner; `"error"` → `ErrorState` with retry calling `refetch()`; otherwise calls `resolveOnboardingGuardAction`; `"redirect_to_profile"` → `<Navigate to="/profile" replace />`; `"render"` → renders `children`
    - _Requirements: 5.1, 5.2_

- [ ] 15. Refactor `Step1ProfileParse` and `Step2Roles` for reuse outside the wizard
  - [ ] 15.1 Add `initialProfile`/`onSaveSuccess` optional props to `frontend/src/screens/onboarding/Step1ProfileParse.tsx`
    - When `initialProfile` is provided, skip the `"input"`/`"split"` phases entirely; initialize `phase` to `"edit"` with `parsedProfile` pre-set to `initialProfile`
    - `handleSave`'s `onSuccess` calls `onSaveSuccess?.() ?? navigate("/onboarding/2")`, preserving current wizard behavior when the prop is omitted
    - _Requirements: 4.3_
  - [ ] 15.2 Add `initialSelectedRoles`/`onSaveSuccess` optional props to `frontend/src/screens/onboarding/Step2Roles.tsx`
    - When `initialSelectedRoles` is provided, `selectedRoles` initializes from it instead of `[]`; the AI suggestion call on mount still runs and augments rather than replaces the existing selection
    - `saveRolesMutation`'s `onSuccess` calls `onSaveSuccess?.() ?? navigate("/onboarding/3")`
    - _Requirements: 4.3_
    - **Mandatory acceptance criterion (do not mark task 15 complete without this):** after applying 15.1 and 15.2, run the full 4-step `OnboardingWizard` end-to-end with the default behavior (no new props passed — i.e. `<Step1ProfileParse/>`/`<Step2Roles/>` exactly as `OnboardingWizard` invokes them today): paste CV → confirm profile, confirm roles, choose companies, first scan. Confirm the observed behavior is identical to the pre-refactor implementation at every step. This repository has no `@testing-library/react` and no component-rendering tests, so this cannot be covered by an automated test — it is the one manual verification this design explicitly requires to be tracked as an acceptance criterion (see `design.md`, Testing Strategy).

- [ ] 16. Checkpoint - Manual onboarding wizard regression verification
  - Run the dev server and manually execute the full onboarding wizard end-to-end (paste CV → confirm profile, confirm roles, choose companies, first scan) with the default (no-new-props) behavior, as described in task 15's acceptance criterion. This is the ONE checkpoint in this plan that requires explicit human confirmation — there is no automated test covering it. STOP here and wait for the user's explicit response before proceeding to task 17. Do not interpret silence or the absence of a response as approval.

- [ ] 17. Implement `ProfileView`
  - [ ] 17.1 Implement `frontend/src/screens/profile/ProfileView.tsx`
    - Reads `profile` from `useProfileData()`; reads `email` via `getEmailFromIdToken(tokenStore.getIdToken() ?? "")`
    - Two sections: "Información de perfil" rendering `<Step1ProfileParse initialProfile={profile.perfilEstructurado} onSaveSuccess={...}/>`, and "Cargos activos" rendering `<Step2Roles initialSelectedRoles={profile.cargosActivos} onSaveSuccess={...}/>`
    - No wizard header, no step navigation, no `Step3Companies`/`Step4Scan` imports, no name field
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [ ] 18. Wire up the `App.tsx` route tree
  - [ ] 18.1 Reorganize routes in `frontend/src/App.tsx`
    - Public: `/callback` (`CallbackView`, no `Layout`), `/onboarding/:step` (`AuthGuard` → `OnboardingGuard` → `OnboardingWizard`, no `Layout`), `*` (public `NotFoundView`, replacing `CatchAllPage`)
    - `Layout` (Navbar + Outlet) wraps: `/` (`RootRoute`, public), `/vacancies`, `/vacancies/:companyId/:vacancyId`, `/applications`, `/applications/:companyId/:vacancyId`, `/sources`, `/profile` (`ProfileView`) — each still individually wrapped in `AuthGuard` except `/`
    - Remove the inline `CatchAllPage` placeholder
    - _Requirements: 3.2, 3.3, 3.6, 7.1, 7.2, 7.3_

- [ ] 19. Final checkpoint - Ensure all tests pass
  - Run the full test suite (`npm run test`) and `npm run build` in `frontend/`. This is auto-verifiable: if both succeed, the plan is complete. If either fails, stop and report the failure instead of reporting completion.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; core implementation tasks (unmarked) are never optional.
- Task 15's manual regression acceptance criterion and task 16 are the explicit reflection, in this task list, of the mandatory manual verification required by `design.md`'s Testing Strategy section — they are not skippable the way `*`-marked test tasks are.
- Property tests use `fast-check`, minimum 100 iterations each, tagged with `// Feature: frontend-navigation, Property N: <title>` per the design document's Correctness Properties.
- No new test dependency is introduced; component-level behavior (visual/aesthetic requirements 9.1–9.4, the "no duplication" aspect of 4.3, and the "retains current implementation" aspect of 5.3) is covered by code review and the manual check in tasks 15–16, consistent with this repository's existing convention of testing pure functions only.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "4.1", "5.1", "6.1", "11.1", "12.1", "12.2", "15.1", "15.2"] },
    { "id": 1, "tasks": ["1.2", "2.2", "3.2", "4.2", "5.2", "6.2", "11.2", "12.3", "13.1"] },
    {
      "id": 2,
      "tasks": ["7"],
      "type": "checkpoint",
      "title": "Checkpoint - Ensure all pure-module tests pass",
      "gate": "auto-verify",
      "verification": "Run `npm run test` (frontend/). If the suite passes, proceed automatically to wave 3 without asking the user for confirmation. If any test fails, STOP and report the failure — do not proceed.",
      "requiresHumanConfirmation": false
    },
    { "id": 3, "tasks": ["8.1", "9.1"] },
    { "id": 4, "tasks": ["8.2"] },
    { "id": 5, "tasks": ["10.1", "14.1"] },
    {
      "id": 6,
      "tasks": ["16"],
      "type": "checkpoint",
      "title": "Checkpoint - Manual onboarding wizard regression verification",
      "gate": "human-confirmation-required",
      "verification": "HARD STOP. This checkpoint depends on the completion of ALL tasks numbered 1.1 through 15.2 (waves 0-5), not only 15.1/15.2. There is no automated test covering this (`@testing-library/react` is not installed in this repo). The runner MUST present clear manual verification instructions to the user (run the dev server, execute the full 4-step onboarding wizard end-to-end: paste CV → confirm profile, confirm roles, choose companies, first scan; confirm default behavior — no new props passed — is identical to the pre-refactor implementation), then WAIT for an explicit human response. Silence or timeout MUST NOT be interpreted as approval. Do not dispatch task 17.1 or any later task until the user explicitly confirms.",
      "requiresHumanConfirmation": true,
      "blocks": ["17.1", "18.1", "19"]
    },
    { "id": 7, "tasks": ["17.1"] },
    { "id": 8, "tasks": ["18.1"] },
    {
      "id": 9,
      "tasks": ["19"],
      "type": "checkpoint",
      "title": "Final checkpoint - Ensure all tests pass",
      "gate": "auto-verify",
      "verification": "Run the full test suite (`npm run test`) and `npm run build` (frontend/). If both succeed, the plan is complete. If either fails, STOP and report the failure — do not report completion.",
      "requiresHumanConfirmation": false
    }
  ],
  "tramos": {
    "A": { "description": "Autonomous execution from task 1.1 through 15.2 inclusive (waves 0-5). No user confirmation needed at any intermediate point unless a test fails, a build error occurs, or a real discrepancy against the actual codebase contradicts design.md — in those cases, stop and report.", "waves": [0, 1, 2, 3, 4, 5] },
    "B": { "description": "Starts only after the user explicitly confirms checkpoint 16 (wave 6). Covers task 17.1 through the final checkpoint 19.", "waves": [7, 8, 9] }
  }
}
```
