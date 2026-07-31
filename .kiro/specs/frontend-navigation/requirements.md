# Frontend Navigation Architecture — Requirements Document

## Introduction

This document specifies the complete frontend navigation structure for the job application platform. The system currently lacks a public landing page, proper routing for authenticated versus unauthenticated users, and a persistent navigation bar. Additionally, user profile management is currently embedded within a multi-step onboarding wizard, but must be refactored into a dedicated, persistent view accessible post-onboarding.

This feature implements four core changes:
1. A public root route ("/") with conditional rendering for authenticated/unauthenticated states
2. A persistent, context-aware navigation bar visible on key routes
3. A standalone profile management screen separated from the onboarding wizard
4. Intelligent post-login redirection based on profile completion status

## Glossary

- **System**: The Frontend SPA (React + Vite + TypeScript, running in the browser)
- **User**: A person interacting with the application
- **Unauthenticated_User**: A user without an active session (no access token in tokenStore)
- **Authenticated_User**: A user with valid access tokens (access_token and id_token in sessionStorage/tokenStore)
- **AuthContext**: React context managing `isAuthenticated`, `login()`, `logout()`, and `handleCallback()` functions
- **AuthGuard**: React component that wraps routes requiring authentication; redirects to `/callback` if not authenticated
- **Profile**: User-specific data stored at endpoint GET/PUT `/me/profile`, including resumen CV, structured skills, experience, education, projects, certifications
- **ProfileNotFound**: HTTP 404 response from GET `/me/profile`, indicating the user has not completed the initial profile upload
- **Post_Login_Redirect**: Route saved in sessionStorage before initiating OAuth flow; used to redirect after successful token exchange
- **Onboarding_Wizard**: Multi-step wizard (`/onboarding/1`, `/onboarding/2`, `/onboarding/3`, `/onboarding/4`) for new users to upload CV, select roles, choose companies, and run initial scan
- **Layout_Component**: React component wrapping authenticated routes with a persistent navigation bar and `<Outlet />` for route content
- **id_token**: JWT containing user claims (sub, email, cognito:username, scope) decoded from OAuth response
- **Cognito_Hosted_UI**: AWS Cognito authorization endpoint for OAuth Authorization Code + PKCE flow
- **Landing_Page**: Public-facing introductory page describing the platform's purpose and value proposition

## Requirements

### Requirement 1: Root Route with Conditional Rendering

**User Story:** As an unauthenticated visitor, I want to see a landing page explaining what the platform does, so that I understand the value proposition before signing in. As an authenticated user, I want to see a dashboard with quick access to key features, so that I can navigate efficiently without redundant marketing.

#### Acceptance Criteria

1. THE System SHALL create a public root route at "/" that is NOT protected by AuthGuard.
2. WHEN an unauthenticated user navigates to "/" (or sessionStorage contains no access_token), THE System SHALL render the Landing_Page component.
3. THE Landing_Page SHALL include:
   - A clear, concise explanation of the platform's purpose (matching a job application workflow for candidates)
   - The platform name/logo prominently displayed
   - A call-to-action button labeled "Iniciar sesión" that invokes the `login()` function from AuthContext
4. WHEN an authenticated user navigates to "/", THE System SHALL render a Dashboard component instead of the Landing_Page.
5. THE Dashboard component SHALL display:
   - A personalized greeting (e.g., "Bienvenido, [email from id_token]")
   - Quick-access card or button to "/vacancies" (label: "Ver Vacantes")
   - Quick-access card or button to "/applications" (label: "Mis Postulaciones")
   - No marketing or feature explanation (avoid content duplication with the landing page)

### Requirement 2: Root Route Redirect Logic in CallbackView

**User Story:** As a new user who has just logged in, I want to be automatically directed to the onboarding wizard if I have not yet uploaded a profile. As a returning user, I want to return to the route I was on before logging in (or the home dashboard if no prior route was saved).

#### Acceptance Criteria

1. WHEN a user completes OAuth authentication and arrives at CallbackView with a valid authorization code, THE System SHALL exchange the code for tokens via handleCallback().
2. AFTER token exchange succeeds, THE System SHALL immediately invoke GET `/me/profile` to check profile existence.
3. IF GET `/me/profile` returns HTTP 200 (profile exists), THE System SHALL redirect to `sessionStorage.getItem('post_login_redirect')` or "/" if the key is missing or empty.
4. IF GET `/me/profile` returns HTTP 404 (ProfileNotFound), THE System SHALL redirect to "/onboarding/1" (start the onboarding wizard).
5. IF GET `/me/profile` returns any other HTTP error (5xx, network failure, etc.), THE System SHALL render an error message with a retry button.
6. THE System SHALL clear sessionStorage keys `post_login_redirect` and `pkce_code_verifier` AFTER completing the redirect (whether to onboarding, post-login-redirect, or "/").

### Requirement 3: Persistent Navigation Bar

**User Story:** As an authenticated user, I want a consistent navigation experience across the main features of the application, so that I can easily move between vacancies, my applications, and account settings without disorientation.

#### Acceptance Criteria

1. THE System SHALL create a Navbar component that displays persistently across multiple routes.
2. THE Navbar SHALL be visible on routes: "/", "/vacancies", "/vacancies/:companyId/:vacancyId", "/applications", "/applications/:companyId/:vacancyId", "/sources", "/profile".
3. THE Navbar SHALL NOT be visible on "/callback" or "/onboarding/:step" (onboarding is full-screen experience).
4. THE Navbar layout SHALL be:
   - **Left section**: Platform name/logo as a clickable link to "/" (opens the root route)
   - **Center/Main section**: Navigation links visible ONLY if the user is authenticated:
     - "Vacantes" (link to "/vacancies")
     - "Postulaciones" (link to "/applications")
     - "Fuentes" (link to "/sources")
   - **Right section**: Context-dependent action buttons:
     - IF unauthenticated: A button labeled "Iniciar sesión" that invokes `login()` from AuthContext
     - IF authenticated: 
       - A link or button labeled "Perfil" that navigates to "/profile"
       - A button labeled "Cerrar sesión" that invokes `logout()` from AuthContext
5. THE System SHALL implement the Navbar via a Layout component that wraps authenticated routes and renders `<Outlet />` for route-specific content.
6. THE Layout component SHALL be conditionally applied: only routes listed in Requirement 3, Criterion 2 use the Layout wrapper.

### Requirement 4: Standalone Profile Management Screen

**User Story:** As an authenticated user with a completed profile, I want a dedicated profile management screen where I can edit my profile information and manage my active job categories, separate from the onboarding flow, so that I can update my information at any time without repeating the full wizard.

#### Acceptance Criteria

1. THE System SHALL create a Profile view at route "/profile" protected by AuthGuard.
2. THE Profile view SHALL assume the user already has an existing profile (i.e., GET `/me/profile` returned HTTP 200).
3. THE Profile view SHALL reuse the existing UI components and validation logic from Step1ProfileParse and Step2Roles without duplication.
4. THE Profile view SHALL NOT include:
   - A multi-step wizard header or progress bar
   - Step navigation buttons to move between profile and roles sections
   - Company selection functionality (Step3Companies)
   - The initial CV scanning feature (Step4Scan)
5. THE Profile view SHALL display a "Profile" heading and be organized into two logical sections:
   - **Section 1: Profile Information** — displaying and allowing edit of PerfilEstructurado (experience, education, projects, certifications, skills)
   - **Section 2: Active Job Roles** — displaying and allowing edit of cargosActivos via PUT `/me/profile/roles`
6. THE Profile view SHALL also display the user's email address (read-only), decoded from the id_token stored in sessionStorage (scope includes "email").
7. THE System SHALL NOT expose a form field for editing the user's name; the name is assumed immutable post-registration.
8. WHEN the user submits profile or roles changes, THE System SHALL call PUT `/me/profile` or PUT `/me/profile/roles` respectively and display success/error feedback inline.

### Requirement 5: Separation of Onboarding and Profile Workflows

**User Story:** As the system, I want to clearly distinguish between the initial onboarding (for new users without a profile) and the profile management workflow (for users with existing profiles), so that new and returning users have appropriate experiences.

#### Acceptance Criteria

1. THE System SHALL reserve route pattern "/onboarding/:step" exclusively for new users who have NOT completed a profile upload.
2. WHEN a user navigates to "/onboarding/:step", THE System SHALL verify via GET `/me/profile` that the user does NOT have an existing profile; if a profile exists, THE System SHALL redirect to "/profile".
3. THE Onboarding_Wizard (accessible via "/onboarding/1", "/onboarding/2", "/onboarding/3", "/onboarding/4") SHALL retain its current implementation:
   - Full-screen layout with multi-step progress bar
   - All four steps (Profile, Roles, Companies, Scan) as currently designed
   - Automatic redirection to "/vacancies" after Step4Scan completion
4. THE Profile view (route "/profile") SHALL be accessible only after profile creation and SHALL serve as the persistent profile management interface.
5. WHEN a user completes onboarding (Step4Scan), THE System SHALL automatically navigate to "/vacancies" (not to "/profile"); profile editing is available via the Navbar link once the user arrives at main features.

### Requirement 6: Post-Login Redirect Preservation

**User Story:** As a user on any page who initiates login, I want to be redirected back to the page I was on after authentication completes, so that my workflow is not interrupted.

#### Acceptance Criteria

1. WHEN the user clicks the "Iniciar sesión" button or invokes `login()` from AuthContext, THE System SHALL save the current URL (pathname + search) to sessionStorage under the key `post_login_redirect`.
2. AFTER successful token exchange in handleCallback(), AND after verifying profile existence (Requirement 2, Criteria 2-4), THE System SHALL redirect to the saved `post_login_redirect` value (or "/" if missing).
3. THE System SHALL clear the `post_login_redirect` key from sessionStorage immediately after using it to prevent unintended reuse on subsequent logins.

### Requirement 7: Routing Structure and AuthGuard Placement

**User Story:** As the routing system, I want clear separation of public and protected routes, so that unauthorized access is prevented and the app structure is maintainable.

#### Acceptance Criteria

1. THE System SHALL organize routes as follows:
   - **Public routes** (NOT wrapped by AuthGuard):
     - "/" (root — conditional landing/dashboard)
     - "/callback" (OAuth callback handler)
     - "*" (NotFound)
   - **Protected routes** (wrapped by AuthGuard):
     - "/onboarding/:step"
     - "/profile"
     - "/vacancies"
     - "/vacancies/:companyId/:vacancyId"
     - "/applications"
     - "/applications/:companyId/:vacancyId"
     - "/sources"
2. THE System SHALL replace the current catch-all route ('*') with a dedicated NotFound page component, rendered as a PUBLIC route (NOT wrapped by AuthGuard) so that it displays correctly regardless of authentication state, with the same visual design system as the rest of the application (same Tailwind palette, typography). The NotFound page SHALL include:
   - A link or button back to '/'
   - IF the user is unauthenticated: an additional 'Iniciar sesión' button that invokes login() from AuthContext, so users who mistyped a protected route's URL have a clear path forward without being force-redirected to Cognito.
   - IF the user is authenticated: THE NotFound page SHALL render within the Layout component (i.e., with the persistent Navbar visible), consistent with Requirement 3.

   > Nota de verificación: verificado contra frontend/src/auth/AuthGuard.tsx que AuthGuard dispara login() automáticamente vía useEffect sin mostrar ningún mensaje al usuario cuando !isAuthenticated, por lo que NotFound debe ser pública para poder mostrar el mensaje de "página no encontrada" en vez de forzar un redirect a Cognito.
3. THE System SHALL NOT render the Navbar for routes outside the list in Requirement 3, Criterion 2.

### Requirement 8: AuthContext Post-Login Behavior

**User Story:** As the authentication system, I want post-login navigation to be intelligent and profile-aware, so that users are routed correctly regardless of onboarding completion.

#### Acceptance Criteria

1. THE AuthContext.handleCallback() function SHALL be refactored to NOT perform any navigation/redirect internally (i.e., remove the existing `window.location.href = savedRoute` line from handleCallback). Its sole responsibilities SHALL be: exchange the authorization code for tokens, persist access_token and id_token via tokenStore, set isAuthenticated to true, and return (resolve) once these steps complete successfully, or throw/reject on failure — exactly as it does today for the error path, unchanged.
2. THE CallbackView component SHALL await the resolved handleCallback() call, and only THEN perform the profile-existence check (GET /me/profile) and the resulting navigation (to /onboarding/1, to post_login_redirect, or to "/"), using React Router's `useNavigate()` (not `window.location.href`, to avoid a full page reload where avoidable) OR window.location.href only if a full reload is specifically required for session/state consistency — this decision SHALL be made explicit and documented in the design phase, with a default preference for `useNavigate()` unless a concrete session/state consistency reason requires a full reload.
3. IF handleCallback() rejects/throws (token exchange failure), THE CallbackView SHALL catch the error and display the existing error state (as implemented today) WITHOUT attempting any profile check or navigation.

   > Nota de verificación: contra el código real de frontend/src/screens/auth/CallbackView.tsx y frontend/src/auth/AuthContext.tsx: actualmente handleCallback() hace window.location.href internamente tras persistir los tokens, y CallbackView solo hace .catch() sobre la promesa sin esperar ningún resultado post-navegación. El nuevo contrato mueve toda la responsabilidad de navegación a CallbackView.

### Requirement 9: Landing Page and Dashboard Styling

**User Story:** As a user, I want a visually cohesive and responsive interface for both the landing page and the dashboard, so that the platform feels polished and professional.

#### Acceptance Criteria

1. THE Landing_Page and Dashboard components SHALL use the same design system (Tailwind CSS classes, color palette, typography) as the rest of the application.
2. THE Landing_Page SHALL be responsive and render correctly on mobile, tablet, and desktop viewports.
3. THE Dashboard SHALL display quick-access cards or buttons in a grid or flex layout that adapts to screen size.
4. THE Navbar SHALL be responsive, with a mobile-friendly hamburger menu or collapsible navigation for narrow viewports.

### Requirement 10: Error Handling and Recovery

**User Story:** As a user, I want clear feedback when something goes wrong during login or profile checks, so that I can take corrective action.

#### Acceptance Criteria

1. IF profile check (GET `/me/profile`) fails with a non-404 HTTP error (e.g., 500, network timeout), THE CallbackView SHALL display a user-friendly error message.
2. THE error message SHALL include a "Reintentar" button that re-invokes the profile check or the full login flow.
3. IF token exchange fails (non-2xx response from token endpoint), THE CallbackView SHALL display an error message and offer a retry button (via `login()`).
4. THE System SHALL log all errors to the browser console in a structured format for debugging purposes.

## Notes

- **Profile Update Path**: When users edit their profile at "/profile", they use PUT `/me/profile` (Requirement 4, Criterion 8). This endpoint updates PerfilEstructurado. The GET `/me/profile` check in CallbackView is a read operation to determine onboarding completion.
- **Email Display**: The user's email is already in the id_token (scope includes "email"). Decoding it client-side requires parsing the JWT; consider using a small JWT decoding library or extracting it in AuthContext and storing it in a stable location.
- **No Name Field**: The Cognito User Pool has `username_attributes = ['email']` (verified against terraform/modules/cognito/main.tf) — meaning `cognito:username` IS the email address, not a person's name. NO name field is displayed or implemented on any screen (landing page, dashboard, or /profile). The only identity data displayed is the email, decoded from the id_token. This is a closed product decision, not a technical limitation — do not propose alternatives for obtaining a name.
- **Component Reuse**: Step1ProfileParse and Step2Roles have their own mutations, forms, and validation. The Profile view should wrap or refactor these to avoid code duplication without breaking the existing onboarding flow.
