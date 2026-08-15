# CRITICAL RULES - MUST FOLLOW

## RESPONSES

- Keep responses concise, direct, and to the point — unless the user explicitly requests a deep dive.

## PLANNING MODE

- Always ask clarifying questions before writing code for complex features.
- Never assume design, tech stack, or AWOS business logic without verifying existing files.
- Use deep-dive sub-agents to assist with research (e.g., CDP log parsing algorithms, TimescaleDB hypertables, LTTB downsampling).

## CHANGE / EDIT MODE
- Never implement features yourself when possible - use sub-agents!
- Identify changes from the plan that can be implemented in parallel, and use sub-agents to implement the features efficiently
- When using sub-agents to implement features, act as a coordinator only
- When implementing large features, act as a coordinator and delegate parallel tasks (e.g., backend API vs. Vue components) to sub-agents.
- Use the best model for the task: premium models for complex Python/FastAPI/Vue coding, mid-tier models for documentation or minor scripts.
- Never modify production database volume paths directly — strictly use the host bind-mount (`/data/monitoring-aloptama/db`) specified in `docker-compose.yml`.
- After completing features (large or small), ALWAYS run verification commands (`pytest` on backend, `npm run build` on frontend).

## GIT & DEPLOYMENT WORKFLOW

- **Coolify Auto-Deployment**: Every `git push` to `origin` automatically triggers a production redeploy via GitHub Webhook.
- **Commit Rules**: OpenCode may stage files and generate semantic commit messages and executing `git commit`. 
- **Push Rules**: OpenCode MUST NEVER run `git push` automatically. Always present the commit summary and ask for explicit user approval before pushing to `origin`.
- **Pre-Push Guarantee**: NEVER request `git push` approval unless all backend tests (`pytest`) and frontend syntax checks have passed 100%.
- **Deployed App URL**: Coolify Auto-Deployment will automaticaly route to https://rhf-monitoring.hilmihanif.my.id/ as endpoint

## DATABASE SCHEMA CHANGES

- Whenever database schema changes are required, ALWAYS create a new sequentially numbered `.sql` file in `backend/migrations/` (e.g., `013_new_feature_schema.sql`).
- NEVER edit or mutate existing migration files (`001_initial_schema.sql` through `012_drop_telemetry.sql`) that have already been executed.
- NEVER run destructive `DROP TABLE` or `RESET_DB_ON_BOOT=true` scripts on production environments.

## TESTING

- Backend: ALWAYS run `pytest` inside `backend/` to verify logic before concluding any task.
- Frontend: Verify Vue component syntax, Tailwind classes, and build readiness (`npm run build` inside `frontend/`).
- Never assume changes simply work — always test with existing mock data and fixtures in `backend/tests/`.

## UI DESIGN & COMPONENT SYSTEM

- Follow the existing Vue 3 (Composition API) + Tailwind CSS + Apache ECharts design patterns.
- Maintain styling consistency across key views (`DashboardView.vue`, `RunwayView.vue`, `SlaOlaView.vue`, `SystemView.vue`).

## INSTALLED SKILLS & MCP TOOLS

- **Find Skills**: `@skills/find-skills` — Search and dynamic discovery of open-source skill modules.
- **UI Testing**: `@skills/playwright-cli` — Headless browser interaction and CLI-based UI screenshot verification.
- **Charts & Data Visualization**: `@skills/chart-designer` — Best practices for Apache ECharts and interactive telemetry graphs.
- **Backend Architecture**: `@skills/fastapi` — Standard async patterns, router design, and FastAPI optimizations.
- **Frontend Standards**: `@skills/vue-best-practices` & `@skills/frontend-design` — Vue 3 Composition API patterns and Tailwind CSS layouts.
- **Database MCP**: `@skills/postgres` & Remote MCP `pg-aiguide` — TimescaleDB query optimization, migration validation, and hypertable analysis.
