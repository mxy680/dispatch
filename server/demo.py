from database import models

# CREATE a project
print("Creating a project...")
pid = models.create_project(
    user_id="demo@case.edu", 
    name="Voice Agent Demo", 
    file_path="/Users/demo/projects/voice-agent"
)
print(f"✅ Created project: {pid}\n")

# READ the project back
print("Retrieving projects...")
projects = models.get_user_projects("demo@case.edu")
print(f"✅ Found: {projects[0]['name']} (Status: {projects[0]['status']})\n")

# CREATE a task
print("Creating a task...")
tid = models.create_task(pid, "Add user authentication")
print(f"✅ Created task: {tid}\n")

# READ tasks
print("Retrieving tasks...")
tasks = models.get_project_tasks(pid)
print(f"✅ Task: {tasks[0]['description']} (Status: {tasks[0]['status']})\n")

# UPDATE task status
print("Updating task to completed...")
models.update_task_status(tid, "completed")
tasks = models.get_project_tasks(pid)
print(f"✅ Task is now: {tasks[0]['status']}")

exit()

