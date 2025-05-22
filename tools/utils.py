import json
import os

def load_tools_config():
    config_path = os.path.join(os.path.dirname(__file__), 'tools.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("tools.json file not found.")
        return {}
    except json.JSONDecodeError:
        print("tools.json is not properly formatted.")
        return {}

def topological_sort(nodes, edges):
    from collections import defaultdict, deque

    graph = defaultdict(list)
    indegree = defaultdict(int)
    node_map = {n['id']: n for n in nodes}

    for edge in edges:
        graph[edge['source']].append(edge['target'])
        indegree[edge['target']] += 1

    queue = deque([node['id'] for node in nodes if indegree[node['id']] == 0])
    sorted_nodes = []

    while queue:
        node_id = queue.popleft()
        sorted_nodes.append(node_map[node_id])
        for neighbor in graph[node_id]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_nodes) != len(nodes):
        raise ValueError("Cycle detected in workflow")

    return sorted_nodes
