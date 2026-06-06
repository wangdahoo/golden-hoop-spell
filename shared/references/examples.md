# Complete Examples

This file contains realistic, fully-populated examples for reference.

## Example 1: Authentication Sprint (features.json)

```json
{
  "project": {
    "name": "Task Manager App",
    "description": "A web application for managing personal tasks and projects",
    "tech_stack": ["react", "node.js", "postgresql", "typescript"],
    "created_at": "2024-01-15"
  },
  "sprints": [
    {
      "id": "sprint-001",
      "name": "Authentication Sprint",
      "goal": "Implement complete user authentication with email/password and social login",
      "status": "in_progress",
      "created_at": "2024-01-15",
      "features": [
        {
          "id": "s1-feat-001",
          "category": "infra",
          "priority": "high",
          "title": "Setup authentication provider",
          "description": "Configure authentication provider (Auth0 or custom JWT) for the application with proper environment variables and secrets",
          "acceptance_criteria": [
            "Auth provider is configured with proper credentials",
            "Environment variables are set in .env file",
            "Connection can be established from the application",
            "Secrets are not committed to repository"
          ],
          "technical_notes": "Use Auth0 for simplicity, or implement custom JWT with bcrypt for password hashing. Store secrets in .env file, add to .gitignore",
          "status": "completed",
          "dependencies": [],
          "estimated_complexity": "small",
          "files_affected": [
            ".env",
            ".gitignore",
            "src/config/auth.ts",
            "package.json"
          ]
        },
        {
          "id": "s1-feat-002",
          "category": "ui",
          "priority": "high",
          "title": "Create login page",
          "description": "Build responsive login UI with email/password form, validation, error display, and social login buttons",
          "acceptance_criteria": [
            "Login form displays correctly on desktop and mobile",
            "Email validation shows error for invalid format",
            "Password field shows/hides password toggle",
            "Error messages display for failed login attempts",
            "Social login buttons (Google, GitHub) are present",
            "Loading state shown during authentication"
          ],
          "technical_notes": "Use React Hook Form for validation. Follow design system in Figma. Include accessibility attributes (aria-labels). Test on Chrome, Firefox, Safari",
          "status": "in_progress",
          "dependencies": ["s1-feat-001"],
          "estimated_complexity": "medium",
          "files_affected": [
            "src/components/LoginForm.tsx",
            "src/components/SocialLoginButtons.tsx",
            "src/styles/Login.module.css"
          ]
        },
        {
          "id": "s1-feat-003",
          "category": "api",
          "priority": "high",
          "title": "Implement login API endpoint",
          "description": "Create backend API endpoint for user authentication that validates credentials and returns JWT token",
          "acceptance_criteria": [
            "POST /api/auth/login returns JWT on valid credentials",
            "Returns 401 for invalid credentials",
            "Returns 400 for malformed request body",
            "JWT includes userId, email, and expiration",
            "Token expires after 7 days",
            "Rate limiting prevents brute force attacks"
          ],
          "technical_notes": "Use bcrypt.compare for password validation. Generate JWT with jsonwebtoken library. Add rate limiting middleware (express-rate-limit)",
          "status": "pending",
          "dependencies": ["s1-feat-001"],
          "estimated_complexity": "medium",
          "files_affected": [
            "src/api/auth/login.ts",
            "src/middleware/rateLimiter.ts",
            "src/lib/jwt.ts"
          ]
        },
        {
          "id": "s1-feat-004",
          "category": "core",
          "priority": "high",
          "title": "Connect login form to API",
          "description": "Wire up the login form UI to call the authentication API and handle responses",
          "acceptance_criteria": [
            "Form submission calls POST /api/auth/login",
            "JWT token stored in secure HTTP-only cookie",
            "User redirected to dashboard on success",
            "Error message shown on failure",
            "Loading state managed correctly",
            "Form disabled during submission"
          ],
          "technical_notes": "Use fetch API or axios. Store token in HTTP-only cookie for security (not localStorage). Use React Context for auth state",
          "status": "pending",
          "dependencies": ["s1-feat-002", "s1-feat-003"],
          "estimated_complexity": "medium",
          "files_affected": [
            "src/hooks/useAuth.ts",
            "src/contexts/AuthContext.tsx",
            "src/components/LoginForm.tsx"
          ]
        },
        {
          "id": "s1-feat-005",
          "category": "data",
          "priority": "high",
          "title": "Create user database schema",
          "description": "Design and implement PostgreSQL schema for user accounts with proper indexing and constraints",
          "acceptance_criteria": [
            "Users table created with required fields",
            "Email has unique constraint",
            "Password field stores hashed passwords only",
            "Indexes on email and createdAt fields",
            "Migration file created and tested",
            "Rollback migration works correctly"
          ],
          "technical_notes": "Use Prisma or Knex migrations. Include fields: id, email, password_hash, created_at, updated_at, email_verified. Never store plain text passwords",
          "status": "completed",
          "dependencies": [],
          "estimated_complexity": "small",
          "files_affected": [
            "migrations/001_create_users.ts",
            "prisma/schema.prisma"
          ]
        },
        {
          "id": "s1-feat-006",
          "category": "ui",
          "priority": "medium",
          "title": "Create registration page",
          "description": "Build user registration form with email validation, password strength indicator, and terms acceptance",
          "acceptance_criteria": [
            "Registration form collects email, password, confirm password",
            "Real-time password strength indicator",
            "Email uniqueness checked on blur",
            "Terms of service checkbox required",
            "Success redirects to email verification page",
            "Accessibility: keyboard navigable, screen reader friendly"
          ],
          "technical_notes": "Reuse validation patterns from LoginForm. Use zxcvbn for password strength. Debounce email uniqueness check to avoid excessive API calls",
          "status": "pending",
          "dependencies": ["s1-feat-001", "s1-feat-005"],
          "estimated_complexity": "medium",
          "files_affected": [
            "src/components/RegisterForm.tsx",
            "src/components/PasswordStrengthIndicator.tsx",
            "src/styles/Register.module.css"
          ]
        }
      ]
    }
  ],
  "metadata": {
    "version": "1.0.0",
    "last_updated": "2024-01-16"
  }
}
```

## Example 2: Sprint Planning Session (progress.md)

```markdown
## Sprint Planning - 2024-01-15
**Agent**: Sprint Agent
**Sprint**: sprint-001 - Authentication Sprint

### Requirements Received
- User authentication with email/password
- Social login with Google and GitHub
- Password reset functionality
- Email verification required
- Secure token storage
- Rate limiting for security

### Features Planned
- Total: 6 features
- High priority: 5 (core authentication flow)
- Medium priority: 1 (registration enhancement)
- Low priority: 0

### Sprint Goal
Implement complete user authentication flow including social login, email verification, and secure token management. Users should be able to register, login, and logout securely.

### Implementation Order
1. s1-feat-001 - Setup auth provider (infra) - COMPLETED
2. s1-feat-005 - Create user database schema (data) - COMPLETED
3. s1-feat-002 - Create login page (ui) - IN PROGRESS
4. s1-feat-003 - Implement login API endpoint (api) - PENDING
5. s1-feat-004 - Connect login form to API (core) - PENDING
6. s1-feat-006 - Create registration page (ui) - PENDING

### Technical Decisions
- Chose Auth0 over custom JWT for faster initial implementation
- Using PostgreSQL with Prisma ORM for user data
- Storing JWT in HTTP-only cookies for XSS protection
- Rate limiting at 5 attempts per minute for login

### Notes
- Password reset functionality deferred to Sprint 2
- Social login buttons in UI but implementation in Sprint 3
- Need to coordinate with design team on login page mockups
```

## Example 3: Coding Session (progress.md)

```markdown
## Session 2 - 2024-01-16
**Agent**: Coding Agent
**Sprint**: sprint-001
**Feature**: s1-feat-002 - Create login page

### Implementation
- Created LoginForm component with email and password fields
- Implemented form validation using React Hook Form
- Added show/hide password toggle button
- Created SocialLoginButtons component with Google and GitHub buttons
- Added loading spinner state during form submission
- Styled components using CSS modules

### Files Changed
- src/components/LoginForm.tsx - Main login form component
- src/components/SocialLoginButtons.tsx - Social login button component
- src/styles/Login.module.css - Login page styles
- src/types/auth.ts - TypeScript types for auth forms

### Tests Performed
- Tested form validation with invalid email format ✓
- Tested required field validation ✓
- Tested password visibility toggle ✓
- Tested responsive layout on mobile (375px) and tablet (768px) ✓
- Tested keyboard navigation (Tab, Enter) ✓
- Tested with screen reader (VoiceOver) ✓
- No console errors ✓
- Lint passes ✓

### Issues Encountered
- Initially used email pattern validation that was too strict, relaxed to accept + signs in emails
- Had to adjust button spacing for mobile view, added media query

### Acceptance Criteria Status
- [x] Login form displays correctly on desktop and mobile
- [x] Email validation shows error for invalid format
- [x] Password field shows/hides password toggle
- [x] Error messages display for failed login attempts (component ready)
- [x] Social login buttons (Google, GitHub) are present
- [x] Loading state shown during authentication (component ready)

### Next Steps
- Ready for s1-feat-003: Implement login API endpoint
- After API is ready, s1-feat-004 will connect form to API
```

## Example 4: Archive Directory Structure

After archiving completed sprint:

```
project-root/
├── features.json          (sprint-001 removed, only sprint-002 remains)
├── progress.md            (updated with archive entry)
├── .agent-harness/
│   └── archived/
│       └── sprint-001_authentication_sprint_20240120_143000/
│           ├── features.json    (complete sprint-001 data)
│           └── progress.md      (all sprint-001 sessions)
```

## Usage Patterns

### Sprint Agent Workflow

1. Read this file and [sprint-agent.md](sprint-agent.md)
2. Archive completed sprints (if any)
3. Analyze user requirements
4. Create features following the authentication sprint example
5. Update `features.json` and `progress.md`

### Coding Agent Workflow

1. Read this file and [coding-agent.md](coding-agent.md)
2. Select ONE feature from current sprint
3. Implement following the coding session example
4. Test thoroughly using checklist
5. Update `progress.md` and `features.json`
