"""
Simple keyword-based prompt refiner (no LLM needed).
Turns raw voice intents into structured coding prompts.
"""

TEMPLATES = {
    "create_project": """
## New Project Setup
Create a new project called "{project_name}".

### Requirements:
- Initialize project structure with proper folder layout
- Create README.md with project description
- Set up basic configuration files
- Add .gitignore

### Expected Output:
- List of files created
- Project structure overview
""",
    "create_task": """
## Implementation Task
**Project:** {project_name}
**Task:** {task_description}

### Requirements:
1. Implement the feature described above
2. Follow existing code patterns in the project
3. Add proper error handling and input validation
4. Include comments explaining the logic
5. Write clean, production-ready code

### Context:
- This is part of the "{project_name}" project
- Follow the existing architecture and conventions

### Expected Output:
- Code files with implementation
- Brief explanation of changes
- Any dependencies needed
""",
    "fix_bug": """
## Bug Fix
**Project:** {project_name}
**Issue:** {task_description}

### Steps:
1. Identify the root cause of the issue
2. Implement the fix with minimal side effects
3. Add a test to prevent regression
4. Document what was changed and why

### Expected Output:
- Fixed code
- Explanation of root cause
- Test case
""",
    "status_check": """
## Status Report
**Project:** {project_name}

Generate a status summary for this project including:
- Current progress overview
- Pending tasks
- Recent completions
""",
    "unknown": """
## General Task
**Description:** {task_description}

Please analyze this request and:
1. Determine what needs to be done
2. Break it into actionable steps
3. Implement the solution
""",
}


def refine_prompt(intent_data: dict) -> str:
    intent = intent_data.get("intent", "unknown")
    template = TEMPLATES.get(intent, TEMPLATES["unknown"])

    return template.format(
        project_name=intent_data.get("project_name", "Unknown"),
        task_description=intent_data.get("task_description", "No description"),
    ).strip()
