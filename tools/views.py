import json
import os
import subprocess
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.conf import settings
import zipfile
import io
import glob
from django.views.decorators.csrf import csrf_exempt
from .models import Workflow
from django.db import IntegrityError
from collections import defaultdict, deque
 
INSTALL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "installed_tools")

TOOLS_JSON_PATH = os.path.join(os.path.dirname(__file__), 'tools.json')

@csrf_exempt
def execute_workflow(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST request required"}, status=400)

    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({"error": "Invalid JSON", "details": str(e)}, status=400)

    workflow_name = data.get("workflow_name") or "unnamed_workflow"
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    node_map = {n["id"]: n for n in nodes}
    edge_map = defaultdict(list)
    for e in edges:
        edge_map[e["target"]].append(e)

    log = []

    # Build dependency graph
    graph = defaultdict(list)
    in_degree = defaultdict(int)
    connected_nodes = set()

    for edge in edges:
        src = edge["source"]
        tgt = edge["target"]
        graph[src].append(tgt)
        in_degree[tgt] += 1
        connected_nodes.update([src, tgt])

    roots = [n for n in connected_nodes if in_degree[n] == 0]
    if len(roots) != 1:
        return JsonResponse({
            "success": False,
            "error": f"Workflow must have exactly one starting tool. Found {len(roots)}: {roots}"
        }, status=400)

    # Topological sort
    sorted_ids = []
    queue = deque(roots)
    while queue:
        current = queue.popleft()
        sorted_ids.append(current)
        for neighbor in graph[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_ids) != len(connected_nodes):
        return JsonResponse({
            "success": False,
            "error": "Workflow contains disconnected or cyclic paths."
        }, status=400)

    # Validate mandatory fields before execution
    for node_id in sorted_ids:
        node = node_map[node_id]
        label = node["data"]["label"]
        if label == "file":
            continue

        parameters = node["data"].get("parameters", {})
        tool_def = node["data"].get("toolDef", {})
        options = tool_def.get("options", [])
        incoming = edge_map.get(node_id, [])

        for opt in options:
            if not opt.get("mandatory"):
                continue

            param_label = opt.get("label")
            val = parameters.get(param_label)
            filled_by_user = val is not None and str(val).strip() != ""
            filled_by_edge = any(e["data"].get("param") == param_label for e in incoming)

            if not filled_by_user and not filled_by_edge:
                return JsonResponse({
                    "success": False,
                    "error": f'Mandatory input "{param_label}" is missing for tool "{label}".'
                }, status=400)

    # Now execute each tool
    for node_id in sorted_ids:
        node = node_map[node_id]
        label = node["data"]["label"]
        if label == "file":
            continue

        parameters = node["data"].get("parameters", {})
        tool_def = node["data"].get("toolDef", {})
        command = [tool_def.get("command", label)]
        resolved_params = {}

        output_dir = os.path.join(settings.MEDIA_ROOT, "my_files", workflow_name, label)
        os.makedirs(output_dir, exist_ok=True)

        incoming = edge_map.get(node_id, [])
        for edge in incoming:
            source_id = edge["source"]
            param_name = edge["data"].get("param")
            source_node = node_map[source_id]
            source_label = source_node["data"]["label"]
            filename = source_node["data"]["parameters"].get("filename")

            if filename:
                if source_label == "file":
                    prior_edge = next((e for e in edges if e["target"] == source_id), None)
                    if prior_edge:
                        producer_id = prior_edge["source"]
                        producer_label = node_map[producer_id]["data"]["label"]
                        source_path = os.path.join(settings.MEDIA_ROOT, "my_files", workflow_name, producer_label, filename)
                    else:
                        source_path = os.path.join(settings.MEDIA_ROOT, "my_files", filename)
                else:
                    source_path = os.path.join(settings.MEDIA_ROOT, "my_files", workflow_name, source_label, filename)

                if not os.path.exists(source_path):
                    return JsonResponse({
                        "success": False,
                        "error": f"File not found: {source_path}",
                        "log": log
                    }, status=500)

                resolved_params[param_name] = source_path

        for opt in tool_def.get("options", []):
            opt_label = opt.get("label")
            opt_flag = opt.get("flag")
            val = resolved_params.get(opt_label) or parameters.get(opt_label)

            if val:
                if opt_flag and (opt_flag == "-o" or opt_flag == "--output" or "output" in opt_label.lower()):
                    base = os.path.basename(str(val))
                    has_extension = "." in base and len(base.split(".")[-1]) > 1

                    if has_extension:
                        sanitized_output = "".join(c for c in base if c.isalnum() or c in ("_", "-", "."))
                        unique_output = generate_unique_filename(output_dir, sanitized_output)
                        final_output_path = os.path.join(output_dir, unique_output)
                        os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
                    else:
                        sanitized_output = "".join(c for c in base if c.isalnum() or c in ("_", "-"))
                        unique_output = generate_unique_filename(output_dir, sanitized_output)
                        final_output_path = os.path.join(output_dir, unique_output)
                        os.makedirs(final_output_path, exist_ok=True)

                    if opt_flag:
                        command += [opt_flag, final_output_path]
                    else:
                        command.append(final_output_path)

                    # Save only filename so downstream nodes can reference it
                    resolved_params[opt_label] = os.path.basename(final_output_path)

                elif opt_flag:
                    command += [opt_flag, str(val)]
                else:
                    command.append(str(val))
            else:
                log.append(f"[WARN] Missing parameter '{opt_label}' for tool '{label}'")

        try:
            command_str = ' '.join(command)
            log.append(f"Running: {command_str}")
            result = subprocess.run(command, cwd=output_dir, capture_output=True, text=True)
            log.append(result.stdout)
            if result.stderr:
                log.append(result.stderr)
            if result.returncode != 0:
                raise Exception(f"Command failed: {result.stderr}")
        except Exception as e:
            return JsonResponse({
                "success": False,
                "error": str(e),
                "log": log
            }, status=500)

    return JsonResponse({"success": True, "log": log})



@csrf_exempt
def delete_workflow(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = data.get("name")
    if not name:
        return JsonResponse({"error": "Missing workflow name"}, status=400)

    try:
        workflow = Workflow.objects.get(name=name)
        workflow.delete()
        return JsonResponse({"success": True})
    except Workflow.DoesNotExist:
        return JsonResponse({"error": f"Workflow '{name}' not found"}, status=404)



@csrf_exempt
def save_workflow(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = data.get("name")
    graph = data.get("graph")

    if not name or not graph:
        return JsonResponse({"error": "Missing workflow name or graph"}, status=400)

    try:
        obj, created = Workflow.objects.update_or_create(
            name=name,
            defaults={"graph": graph}
        )
        return JsonResponse({"success": True, "created": created})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def load_workflows(request):
    workflows = Workflow.objects.all().order_by('-created_at')
    data = [
        {"id": wf.id, "name": wf.name, "graph": wf.graph}
        for wf in workflows
    ]
    return JsonResponse(data, safe=False)

def get_tools_json(request):
    tools_path = os.path.join(settings.BASE_DIR, 'tools', 'tools.json')
    with open(tools_path, 'r') as f:
        tools = json.load(f)
    return JsonResponse(tools)

def workflow_editor(request):
    react_static_path = os.path.join(settings.BASE_DIR, 'tools', 'static', 'react', 'static')

    js_files = glob.glob(os.path.join(react_static_path, 'js', 'main*.js'))
    css_files = glob.glob(os.path.join(react_static_path, 'css', 'main*.css'))

    context = {
        'react_js': os.path.relpath(js_files[0], os.path.join(settings.BASE_DIR, 'tools', 'static')),
        'react_css': os.path.relpath(css_files[0], os.path.join(settings.BASE_DIR, 'tools', 'static')),
    }

    return render(request, 'tools/workflow_editor.html', context)

def delete_tool(request):
    if request.method == "POST":
        tool_name = request.POST.get("tool_name")
        try:
            with open(TOOLS_JSON_PATH, 'r+') as file:
                tools = json.load(file)
                if tool_name in tools:
                    del tools[tool_name]
                    file.seek(0)
                    json.dump(tools, file, indent=4)
                    file.truncate()
                    return JsonResponse({"success": True, "message": f"Tool '{tool_name}' deleted successfully."})
                else:
                    return JsonResponse({"success": False, "message": "Tool not found."})
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})
    return JsonResponse({"success": False, "message": "Invalid request method."})

def tool_deletion(request):
    try:
        with open(TOOLS_JSON_PATH, 'r') as file:
            tools = json.load(file)
        return render(request, 'tools/tool_deletion.html', {'tools': tools})
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error loading tools: {str(e)}"})

def tool_help(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            tool_name = data.get("tool_name")

            if not tool_name:
                return JsonResponse({"error": "Tool command is required."}, status=400)

            # Run the help command
            result = subprocess.run(
                f"{tool_name} --help", shell=True, capture_output=True, text=True, check=False
            )

            if result.returncode != 0:
                return JsonResponse({
                    "error": f"Failed to get help for '{tool_name}': {result.stderr.strip()}"
                }, status=500)

            return JsonResponse({
                "success": True,
                "help_output": result.stdout.strip()
            })

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=405)

def install_tool(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            tool_name = data.get("name")
            install_command = data.get("install_command", "").strip()
            autodetect_install = data.get("autodetect_install", False)

             
            commands = [
                f"apt-get update",
                f"apt-get install -y {tool_name}",
                f"apt install {tool_name}",
                f"pip3 install {tool_name}",
                f"brew install {tool_name}",
                f"conda install -y {tool_name}"
                f"cconda install -c bioconda {tool_name}"
            ] if autodetect_install else [install_command]

            print(f"Autodetect Install: {autodetect_install}")
            print(f"Commands to Try: {commands}")

            for command in commands:
                try:
                    print(f"Trying command: {command}")
                    process = subprocess.run(
                        command,
                        shell=True,
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    print(f"Command Output (stdout):\n{process.stdout}")
                    print(f"Command Errors (stderr):\n{process.stderr}")

                     
                    tool_path = os.path.join(INSTALL_DIR, tool_name)
                    os.makedirs(tool_path, exist_ok=True)

                     
                    if "pip3 install" in command:
                        version_command = f"python3 -m {tool_name} --version"
                    else:
                        version_command = f"{tool_name} --version"

                    print(f"Checking version with command: {version_command}")
                    version_result = subprocess.run(
                        version_command,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    print(f"Version Output:\n{version_result.stdout}")
                    print(f"Version Errors:\n{version_result.stderr}")

                    version = version_result.stdout.strip()

                    return JsonResponse({
                        "success": True,
                        "message": f"Tool '{tool_name}' installed successfully.",
                        "version": version,
                        "install_dir": tool_path
                    })

                except subprocess.CalledProcessError as e:
                    print(f"Command failed: {command}")
                    print(f"Error Output:\n{e.stderr}")
                    continue

            return JsonResponse({
                "success": False,
                "error": f"Failed to install the tool '{tool_name}' with any method. Try using manual installation"
            })

        except json.JSONDecodeError:
            return JsonResponse({
                "success": False,
                "error": "Invalid JSON data in the request."
            })

    return JsonResponse({"success": False, "error": "Invalid request method."})

# Index Page
def index(request):
    return render(request, 'tools/index.html')


def get_directory_structure(root_dir):
    """
    Recursively gathers files and directories from the specified root directory.
    """
    structure = {}
    for root, dirs, files in os.walk(root_dir):
        relative_path = os.path.relpath(root, root_dir)
        current_level = structure

         
        if relative_path != ".":
            for part in relative_path.split(os.sep):
                current_level = current_level.setdefault(part, {})

         
        current_level["files"] = [
            {
                "name": f,
                "path": os.path.relpath(os.path.join(root, f), settings.MEDIA_ROOT)   
            }
            for f in files
        ]

    return structure

def files(request):
    """
    View for rendering the My Files page, showing all directories and files under media/my_files.
    """
    media_root = os.path.join(settings.MEDIA_ROOT, "my_files")
    tools = {}

    if os.path.exists(media_root):
        for tool_name in os.listdir(media_root):
            tool_path = os.path.join(media_root, tool_name)
            if os.path.isdir(tool_path):
                tools[tool_name] = get_directory_structure(tool_path)

    return render(request, "tools/files.html", {"output_files": tools})

from django.http import FileResponse
# Download Folder as ZIP
def download_folder(request, folder_path):
    """
    Creates a ZIP file of the specified folder and returns it as a download response.
    """
    full_folder_path = os.path.join(settings.MEDIA_ROOT, "my_files", folder_path)

    if os.path.exists(full_folder_path) and os.path.isdir(full_folder_path):
         
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for root, _, files in os.walk(full_folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, full_folder_path)
                    zip_file.write(file_path, arcname)
        zip_buffer.seek(0)

         
        folder_name = os.path.basename(folder_path)
        response = FileResponse(zip_buffer, as_attachment=True, filename=f"{folder_name}.zip")
        return response
    else:
        return JsonResponse({"status": "error", "message": "Folder not found."})

def delete_file(request):
    """
    Deletes a specific file.
    """
    if request.method == "POST":
        file_path = request.POST.get("file_path")
        full_path = os.path.join(settings.MEDIA_ROOT, file_path)

        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                os.remove(full_path)
                return JsonResponse({"status": "success"})
            except Exception as e:
                return JsonResponse({"status": "error", "message": str(e)})
        else:
            return JsonResponse({"status": "error", "message": "File not found."})

    return JsonResponse({"status": "error", "message": "Invalid request method."})

import shutil
def delete_folder(request):
    """
    Deletes a folder and its contents, including nested folders.
    Redirects to the same page after deletion.
    """
    if request.method == "POST":
        folder_path = request.POST.get("folder_path")
        full_path = os.path.join(settings.MEDIA_ROOT, "my_files", folder_path)

        if os.path.exists(full_path) and os.path.isdir(full_path):
            try:
                shutil.rmtree(full_path)
            except Exception as e:
                 
                pass
        
         
        return redirect(request.META.get('HTTP_REFERER', '/'))   

     
    return redirect('/')

def add_tool(request):
    if request.method == "POST": 
        try:
             
            data = json.loads(request.body)

            name = data.get("name")
            description = data.get("description", "")
            install_command = data.get("install_command", "")
            command = data.get("command", "")   
            options = data.get("options", [])

            if not name:
                return JsonResponse({"error": "Tool name is required."}, status=400)
            if not command:
                return JsonResponse({"error": "Command template is required."}, status=400)

             
            validated_options = []
            for opt in options:
                 
                if "label" not in opt or "type" not in opt:
                    return JsonResponse({"error": "Each option must have a label and a type."}, status=400)
                
                 
                validated_options.append({
                    "label": opt["label"],
                    "flag": opt.get("flag"),   
                    "type": opt["type"],
                    "mandatory": opt.get("mandatory", False)   
                })

             
            tools_json_path = os.path.join(settings.BASE_DIR, "tools", "tools.json")
            if not os.path.exists(tools_json_path):
                os.makedirs(os.path.dirname(tools_json_path), exist_ok=True)
                with open(tools_json_path, "w") as f:
                    json.dump({}, f)

             
            with open(tools_json_path, "r+") as f:
                tools = json.load(f)

                 
                if name in tools:
                    return JsonResponse({"error": f"Tool '{name}' already exists."}, status=400)

                # Add new tool to tools.json
                tools[name] = {
                    "description": description,
                    "install_command": install_command,
                    "command": command,
                    "options": validated_options,   
                }

                 
                f.seek(0)
                json.dump(tools, f, indent=4)
                f.truncate()

            return JsonResponse({"success": True, "message": "Tool added successfully."})

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON payload."}, status=400)

        except Exception as e:
            return JsonResponse({"error": f"An unexpected error occurred: {str(e)}"}, status=500)

     
    if request.method == "GET":
        return render(request, "tools/tool_addition.html")

    return JsonResponse({"error": "Invalid request method."}, status=405)



def run_tool(request):
    if request.method == "POST":
        try:
            selected_tool = request.POST.get("tool")
            tools_json_path = os.path.join(settings.BASE_DIR, "tools", "tools.json")

            with open(tools_json_path, "r") as f:
                tools = json.load(f)

            if selected_tool not in tools:
                return JsonResponse({"error": "Invalid tool selected."}, status=400)

            tool = tools[selected_tool]
            base_command = tool["command"]

             
            for placeholder, details in tool["options"].items():
                if details["mandatory"]:
                    value = request.FILES.get(placeholder) or request.POST.get(placeholder)
                    if not value:
                        return JsonResponse({"error": f"Missing value for mandatory option: {details['label']}."}, status=400)
                    base_command += f" {value}" if not details.get("flag") else f" {details['flag']} {value}"

             
            for flag, details in tool["options"].items():
                if not details["mandatory"] and request.POST.get(f"{flag}_enabled"):
                    value = request.POST.get(flag) or request.FILES.get(flag)
                    base_command += f" {flag} {value}" if details.get("flag") else f" {value}"

             
            result = subprocess.run(base_command, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                return JsonResponse({"error": result.stderr}, status=400)

            return JsonResponse({"success": True, "output": result.stdout})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=405)


def generate_unique_filename(directory, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename
    while os.path.exists(os.path.join(directory, unique_filename)):
        unique_filename = f"{base}_{counter}{ext}"
        counter += 1
    return unique_filename


def tool_selector(request):
    tools_json_path = os.path.join(settings.BASE_DIR, "tools", "tools.json")

    try:
         
        with open(tools_json_path, "r") as f:
            tools = json.load(f)
    except FileNotFoundError:
        tools = {}

    selected_tool = request.GET.get("tool")
    tool_details = None

     
    if selected_tool and selected_tool in tools:
        tool_details = tools[selected_tool]

    if request.method == "POST":
        form_data = request.POST
        file_data = request.FILES

        # Base command
        configured_command = tool_details["command"]

        # Directory structure: media/my_files/<tool_name>
        tool_base_dir = os.path.join(settings.MEDIA_ROOT, "my_files", selected_tool)
        os.makedirs(tool_base_dir, exist_ok=True)

         
        for option in tool_details["options"]:
            label = option["label"]
            flag = option.get("flag")   
            input_type = option["type"]

             
            if input_type == "file":
                file_path = form_data.get(label, "").strip()

                # If the file is uploaded, save it under the tool's directory
                if label in file_data:
                    uploaded_file = file_data[label]
                    unique_filename = generate_unique_filename(tool_base_dir, uploaded_file.name)
                    file_path = os.path.join(tool_base_dir, unique_filename)
                    with open(file_path, "wb") as f:
                        for chunk in uploaded_file.chunks():
                            f.write(chunk)

                 
                if not os.path.isfile(file_path):
                    return JsonResponse({
                        "success": False,
                        "error_output": f"File '{file_path}' does not exist. Please provide a valid file path."
                    })

                 
                if flag:
                    configured_command += f" {flag} {file_path}"
                else:
                    configured_command += f" {file_path}"

            # Handle custom output directories or files
            elif input_type == "text" and (flag == "-o" or flag == "--output" or "output" in label.lower()):
                output_path = form_data.get(label, "").strip()

                if output_path:
                     
                    if "." in os.path.basename(output_path) and len(output_path.split(".")[-1]) > 1:
                         
                        sanitized_output = "".join(c for c in output_path if c.isalnum() or c in ("_", "-", "."))
                        unique_output_file = generate_unique_filename(tool_base_dir, sanitized_output)
                        output_file = os.path.join(tool_base_dir, unique_output_file)

                         
                        os.makedirs(os.path.dirname(output_file), exist_ok=True)

                        if flag:
                            configured_command += f" {flag} {output_file}"
                        else:
                            configured_command += f" {output_file}"
                    else:
                         
                        sanitized_output = "".join(c for c in output_path if c.isalnum() or c in ("_", "-"))
                        unique_output_dir = generate_unique_filename(tool_base_dir, sanitized_output)
                        output_dir = os.path.join(tool_base_dir, unique_output_dir)
                        os.makedirs(output_dir, exist_ok=True)

                        if flag:
                            configured_command += f" {flag} {output_dir}"
                        else:
                            configured_command += f" {output_dir}"

             
            elif input_type in ["text", "number"] and label in form_data:
                value = form_data[label].strip()
                if value:
                    if flag:
                        configured_command += f" {flag} {value}"
                    else:
                        configured_command += f" {value}"

        # Run the command in the terminal as a subprocess
        try:
            print(f"Executing command: {configured_command}")   

            result = subprocess.run(
                configured_command,
                shell=True,
                cwd=tool_base_dir,   
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

             
            print(f"Command Output:\n{result.stdout}")

            if result.returncode != 0:
                print(f"Command Error: Non-zero return code detected. Full output:\n{result.stdout.strip()}")
                return JsonResponse({
                    "success": False,
                    "error_output": result.stdout.strip()
                })

             
            return JsonResponse({
                "success": True,
                "message": "Tool executed successfully! Your files are available in 'My Files'.",
                "output": result.stdout.strip()
            })

        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}")   
            return JsonResponse({
                "success": False,
                "error_output": f"An unexpected error occurred: {str(e)}"
            })

     
    return render(request, "tools/tool_selector.html", {
        "tools": tools,
        "selected_tool": selected_tool,
        "tool_details": tool_details,
    })
