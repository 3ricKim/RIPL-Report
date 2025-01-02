import pandas as pd
from pandas import json_normalize
import json5
import json
import re
import os
from logs import logger


# def parse_thought_action(dict_str):
#     thought_action = {}
#     thought_match = re.search(r"'thought':\s*(.+?)\s*,\s*'action'", dict_str)
#     action_match = re.search(r"'action':\s*(.+?)\s*}", dict_str)
#     thought = thought_match.group(1) if thought_match else None
#     thought = thought.replace("\\", "").replace("\"", "").replace("\'", "")
#     action = action_match.group(1) if action_match else None
#     action = action.replace("\\", "").replace("\"", "").replace("\'", "")
#     thought_action = {"thought": thought, "action": action}
#     return thought_action
import re

def parse_thought_action(input_data):
    """
    If input_data is already a dictionary, just return it (or extract subfields).
    If it's a string, parse using regex or JSON logic.
    """
    # Case 1: Already a dictionary
    if isinstance(input_data, dict):
        # Return it as-is, or rename subfields as needed.
        # e.g., ensure keys "thought", "action", "reflection" exist.
        return {
            "thought": input_data.get("thought", "N/A"),
            "action": input_data.get("action", "N/A"),
            "reflection": input_data.get("reflection", "N/A"),
        }

    # Case 2: It's a string that needs parsing
    elif isinstance(input_data, str):
        # Example: If it’s some serialized Python dict string with `'thought': ...`
        # you can do your existing regex-based approach or JSON parsing here
        thought_match = re.search(r"'thought':\s*(.+?)\s*,\s*'action'", input_data)
        action_match = re.search(r"'action':\s*(.+?)\s*(,\s*'reflection'|})", input_data)
        reflection_match = re.search(r"'reflection':\s*(.+?)\s*}", input_data)

        thought = thought_match.group(1) if thought_match else "N/A"
        action = action_match.group(1) if action_match else "N/A"
        reflection = reflection_match.group(1) if reflection_match else "N/A"

        # Clean up any escaped quotes or unwanted characters
        for old, new in [("\\", ""), ("\"", ""), ("'", "")]:
            thought = thought.replace(old, new)
            action = action.replace(old, new)
            reflection = reflection.replace(old, new)

        return {
            "thought": thought.strip(),
            "action": action.strip(),
            "reflection": reflection.strip()
        }

    # Case 3: Unexpected type
    else:
        logger.warning(f"parse_thought_action received unexpected type: {type(input_data)}")
        return {"thought": "N/A", "action": "N/A", "reflection": "N/A"}



def enum_to_action_str():
    action_types = [
        ("NONE", 0),
        ("CLICK", 1),
        ("GOTO", 2),
        ("GOOGLE_SEARCH", 3),
        ("FILL_FORM", 4),
        ("SWITCH_TAB", 5),
        ("GO_BACK", 6),
        ("FILL_SEARCH", 7),
        ("SELECT_OPTION", 8),
        ("HOVER", 9),
        ("SCROLL_DOWN", 10),
        ("SCROLL_UP", 11),
        ("CACHE_DATA", 12),
        ("GET_FINAL_ANSWER", 13)
    ]
    action_dict = {str(value): name for name,
    value in action_types if name.isupper()}
    return action_dict


def to_dict(input_string):
    pattern = r"('action_type'|'element_id'|'url'|'fill_text'):\s*(<[^>]+>|\d+|'[^']+'|\"[^\"]+\")"
    matches = re.findall(pattern, input_string)
    extracted_fields = {}
    for match in matches:
        field_name, field_value = match
        if field_value.startswith('<') and field_value.endswith('>'):
            enum_name = field_value.split('.')[-1].strip('<> ')
            extracted_fields[field_name.strip("'")] = enum_name
        else:
            extracted_fields[field_name.strip("'")] = field_value.strip("'")
    action_dict = enum_to_action_str()
    extracted_fields["action_type"] = action_dict[str(
        extracted_fields["action_type"])].lower()
    extracted_fields["fill_text"] = extracted_fields["fill_text"] if extracted_fields.get(
        "fill_text") else ""
    action = ""
    if "google_search" in extracted_fields["action_type"].lower():
        action = "google_search" + "[" + extracted_fields["fill_text"] + "]"
    elif "fill_search" in extracted_fields["action_type"].lower():
        action = "fill_search" + \
                 "[" + str(extracted_fields["element_id"]) + "," + \
                 extracted_fields["fill_text"] + "]"
    elif "fill_form" in extracted_fields["action_type"].lower():
        action = "fill_search" + \
                 "[" + str(extracted_fields["element_id"]) + "," + \
                 extracted_fields["fill_text"] + "]"
    elif "select_option" in extracted_fields["action_type"].lower():
        action = "select_option" + \
                 "[" + str(extracted_fields["element_id"]) + "," + \
                 extracted_fields["fill_text"] + "]"
    elif "goto" in extracted_fields["action_type"].lower() and extracted_fields.get('url'):
        action = "goto" + "[" + extracted_fields["url"] + "]"
    elif "click" in extracted_fields["action_type"].lower():
        action = "click" + "[" + str(extracted_fields["element_id"]) + "]"
    elif "go_back" in extracted_fields["action_type"].lower():
        action = "go_back" + "[" + str(extracted_fields["element_id"]) + "]"
    elif "none" in extracted_fields["action_type"].lower():
        action = "None"
    elif "cache_data" in extracted_fields["action_type"].lower():
        action = "cache_data" + "[" + extracted_fields["fill_text"] + "]"
    elif "final_answer" in extracted_fields["action_type"].lower():
        action = "get_final_answer" + "[" + extracted_fields["fill_text"] + "]"
    return action


def score_rate(score):
    first, second = score.split("/")
    return float(first) / float(second)


def parse_step_reward(dict_str):
    score_description = {}
    score_match = re.search(r"'score':\s*(.+?)\s*,\s*'description'", dict_str)
    description_match = re.search(r"'description':\s*(.+?)\s*}", dict_str)
    score = score_match.group(1) if score_match else None
    score = score.replace("\\", "").replace("\"", "").replace("\'", "")
    description = description_match.group(1) if description_match else None
    description = description.replace(
        "\\", "").replace("\"", "").replace("\'", "")
    score_description = {"score": score, "description": description}
    return score_description


def process_step_reward(dict_str):
    if dict_str.lower() == "{}":
        dict_str = {}
    elif dict_str.lower() == "finished":
        dict_str = {"score:": 10, "description": "finished"}
    else:
        dict_str = parse_step_reward(dict_str)
    return dict_str


# def write_task_result_to_df(each_task_json_file_path):
#     with open(each_task_json_file_path) as f:
#         data = json.load(f)
#     step_list = data["step_list"]
#     task_name = data["task_name"]
#     task_status = data["status"]
#     reference_task_length = data["reference_task_length"]
#     evaluate_steps = data["evaluate_steps"]
#     for idx, item in enumerate(step_list):
#         for key in item:
#             step_list[idx][key] = str(step_list[idx][key])
#     data_df = json_normalize(step_list, errors='ignore')
#     return task_name, task_status, reference_task_length, evaluate_steps, data_df
def write_task_result_to_df(each_task_json_file_path):
    """Process individual task files into a DataFrame."""
    try:
        with open(each_task_json_file_path) as f:
            data = json.load(f)

        logger.info(f"Loaded data from {each_task_json_file_path}")
        step_list = data.get("step_list", [])

        if not step_list:
            logger.error(f"Step list is empty for task {data.get('task_name', 'Unknown')}")
            return "Unknown", "Unknown", 0, [], pd.DataFrame()

        # Log missing execute_action fields in step_list
        for idx, step in enumerate(step_list):
            if "execute_action" not in step:
                logger.warning(
                    f"Missing 'execute_action' in step {idx} "
                    f"for task {data.get('task_name', 'Unknown')}. Step content: {step}"
                )
                # Provide a default if you want to ensure every step has something
                step["execute_action"] = {}

        # Normalize steps into a DataFrame
        data_df = json_normalize(step_list, errors="ignore")
        logger.info(f"DataFrame after normalization: {data_df.head()}")

        # Handle 'current_trace' if missing after normalization
        if "current_trace" not in data_df:
            logger.warning("'current_trace' column is missing. Extracting manually.")
            current_traces = [
                step.get("current_trace", {"thought": "N/A", "action": "N/A", "reflection": "N/A"})
                for step in step_list
            ]
            data_df["current_trace"] = current_traces

        # Extract fields from 'current_trace'
        data_df["thought"] = data_df["current_trace"].apply(
            lambda x: x.get("thought", "N/A") if isinstance(x, dict) else "N/A"
        )
        data_df["action"] = data_df["current_trace"].apply(
            lambda x: x.get("action", "N/A") if isinstance(x, dict) else "N/A"
        )
        data_df["reflection"] = data_df["current_trace"].apply(
            lambda x: x.get("reflection", "N/A") if isinstance(x, dict) else "N/A"
        )

        # Ensure 'task_score' is extracted
        if "score" in data_df:
            data_df["task_score"] = data_df["score"].apply(
                lambda x: x if isinstance(x, str) else "0 / 1"
            )
        else:
            logger.error("'score' column missing in DataFrame. Defaulting task_score to '0 / 1'")
            data_df["task_score"] = "0 / 1"

        return (
            data.get("task_name", "Unknown"),
            data.get("status", "Unknown"),
            data.get("reference_task_length", 0),
            data.get("evaluate_steps", []),
            data_df
        )

    except Exception as e:
        logger.error(f"Error processing file {each_task_json_file_path}: {e}")
        return "Unknown", "Unknown", 0, [], pd.DataFrame()


#ADDED
def handle_empty_json_result(json_result_path):
    logger.error(f"The folder {json_result_path} is empty. Ensure tasks are processed correctly.")
    # Optional: Create an empty placeholder file for debugging
    placeholder_path = os.path.join(json_result_path, "empty_placeholder.json")
    with open(placeholder_path, 'w') as f:
        json.dump({"message": "This is a placeholder file for debugging."}, f)
    logger.info(f"Created placeholder file: {placeholder_path}")



# def write_to_json(df):
#     df["step_index"] = df["step_index"].apply(lambda x: int(x))
#     df["trace_to_dict"] = df["current_trace"].apply(
#         lambda x: parse_thought_action(x))
#     df["action_to_str"] = df["execute_action"].apply(lambda x: to_dict(x))
#     df["score_rate"] = df["score"].apply(lambda x: score_rate(x))
#     df["step_reward"] = df["step_reward"].apply(
#         lambda x: process_step_reward(x))
#     df["selector"] = df["selector"].fillna("None")
#     df["match_result"] = df["match_func_result"]
#     df["element_value"] = df["element_value"].fillna("None")
#     df["error"] = df["error_message"].fillna("None")
#     df["step_url"] = df["step_url"].fillna("None")
#     df_copy = df[
#         [
#             "step_index",
#             "trace_to_dict",
#             "selector",
#             "action_to_str",
#             "score",
#             "score_rate",
#             "step_reward",
#             "step_url",
#             "match_result",
#             "element_value",
#             "error"
#         ]
#     ]

#     def summary(x):
#         dic = {
#             "step_index": x["step_index"],
#             "trace_description": x["trace_to_dict"] if x["trace_to_dict"] else {},
#             "selector": x["selector"] if x["selector"] != "None" else "",
#             "element_value": x["element_value"] if x["element_value"] != "None" else "",
#             "action": x["action_to_str"] if x["action_to_str"] else "",
#             "task_score": x["score"],
#             "task_score_rate": x["score_rate"],
#             "current_reward_score_description": x["step_reward"],
#             "url": x["step_url"],
#             "match_result": x["match_result"],
#             "error": x["error"] if x["error"] != "None" else ""
#         }
#         # print(dic["match_result"])
#         return dic

#     step_list = []
#     df_copy.apply(lambda x: step_list.append(summary(x)), axis=1)
#     return step_list

def write_to_json(df):
    """Transform the DataFrame into a structured JSON for output."""
    try:
        logger.info(f"Initial DataFrame: {df.head()}")

        # If 'current_trace' doesn't exist, log a warning but continue
        if "current_trace" not in df:
            logger.warning("Missing 'current_trace' column in DataFrame.")

        # Ensure we parse the current_trace into a dictionary (thought/action/reflection)
        df["trace_to_dict"] = df["current_trace"].apply(
            lambda x: parse_thought_action(x) if isinstance(x, dict) else {"thought": "N/A", "action": "N/A"}
        ) if "current_trace" in df else [{} for _ in range(len(df))]
        logger.info(f"Processed 'trace_to_dict': {df['trace_to_dict'].head() if 'trace_to_dict' in df else 'N/A'}")

        # Create a summary dictionary for each row
        def summary(row):
            return {
                "step_index": row.get("step_index", -1),
                "trace_description": row.get("trace_to_dict", {}),
                "selector": row.get("selector", ""),
                "element_value": row.get("element_value", ""),
                # Provide a fallback if 'execute_action' is missing
                "action": row.get("execute_action", {}),
                "task_score": row.get("task_score", "0 / 1"),
                "step_url": row.get("step_url", ""),
                "match_result": row.get("match_func_result", []),
                "error": row.get("error_message", "")
            }

        step_list = []
        df.apply(lambda row: step_list.append(summary(row)), axis=1)
        return step_list

    except Exception as e:
        logger.error(f"Error in write_to_json: {e}")
        return []





# def get_result(input_json_path):
#     json_result_path = input_json_path + "/json_result"
#     out_file_path = input_json_path + "/result"
#     task_list = []
#     for _, filename in enumerate(os.listdir(json_result_path)):
#         file_path = os.path.join(json_result_path, filename)
#         out_json = {}
#         task_name, task_status, reference_task_length, evaluate_steps, data_df = write_task_result_to_df(
#             file_path)
#         out_json["task_id"] = int(filename.split("_")[0])
#         out_json["task_name"] = task_name
#         out_json["task_status"] = task_status
#         if os.path.isfile(file_path):
#             task_step_list = write_to_json(data_df)
#             out_json["step_list"] = task_step_list
#             out_json["evaluation"] = evaluate_steps
#             task_list.append(out_json)

#     task_list = sorted(task_list, key=lambda x: x['task_id'])

#     if not os.path.exists(out_file_path):
#         os.makedirs(out_file_path)
#     out_json_file_path = out_file_path + '/out.json'
#     with open(out_json_file_path, 'w') as json_file:
#         json.dump(task_list, json_file)
#     return out_file_path

def get_result(input_json_path):
    json_result_path = os.path.join(input_json_path, "json_result")
    out_file_path = os.path.join(input_json_path, "result")
    task_list = []

    # Debug: Check if the folder exists
    if not os.path.exists(json_result_path):
        logger.error(f"Directory does not exist: {json_result_path}")
        return None

    # Debug: Check if the folder is empty
    files = os.listdir(json_result_path)
    if not files:
        handle_empty_json_result(json_result_path)
        logger.error(f"No files found in the json_result_path: {json_result_path}")
        logger.error("Ensure tasks are correctly processed and saved in this directory.")
        return None
    logger.info(f"Processing files in: {json_result_path}")

    # Process each file in the json_result_path
    for _, filename in enumerate(files):
        file_path = os.path.join(json_result_path, filename)
        logger.info(f"Processing file: {file_path}")

        try:
            # Debug: Check if the file is valid
            if not os.path.isfile(file_path):
                logger.error(f"Invalid file: {file_path}")
                continue

            with open(file_path, 'r') as f:
                file_data = json.load(f)
                logger.info(f"File loaded successfully: {filename}")

            # Process the task file into a structured output
            task_name, task_status, reference_task_length, evaluate_steps, data_df = write_task_result_to_df(file_path)

            # Debug: Log task details
            logger.info(f"Task Name: {task_name}, Status: {task_status}, Reference Length: {reference_task_length}")

            out_json = {
                "task_id": int(filename.split("_")[0]),
                "task_name": task_name,
                "task_status": task_status,
                "step_list": write_to_json(data_df) if not data_df.empty else [],
                "evaluation": evaluate_steps,
            }
            task_list.append(out_json)

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            continue

    # Sort and save the output JSON
    task_list = sorted(task_list, key=lambda x: x['task_id'])

    if not os.path.exists(out_file_path):
        os.makedirs(out_file_path)

    out_json_file_path = os.path.join(out_file_path, 'out.json')
    logger.info(f"Writing output JSON to: {out_json_file_path}")

    with open(out_json_file_path, 'w') as json_file:
        json.dump(task_list, json_file)
    return out_file_path



def read_json_result(file_path):
    with open(file_path) as f:
        data = json.load(f)
    last_action_result_list = []
    for items in data:
        data_dic = {}
        data_dic["task_id"] = items["task_id"]
        data_dic["task_name"] = items["task_name"]
        data_dic["status"] = items["task_status"]
        data_dic["steps"] = items["step_list"][-1]["step_index"] + 1
        data_dic["task_score"] = items["step_list"][-1]["task_score"]
        data_dic["task_score_rate"] = items["step_list"][-1]["task_score_rate"]
        data_dic["reward_count"] = len(items["evaluation"])
        last_action_result_list.append(data_dic)
    return last_action_result_list


def calculate_total_score(scores):
    molecular_sum = sum(float(x.split('/')[0]) for x in scores)
    denominator_sum = sum(float(x.split('/')[1]) for x in scores)
    final_score = molecular_sum / denominator_sum
    return final_score


import os
import json
import pandas as pd
from logs import logger

def evaluate(file_path, total_token_cost):
    """
    Reads the out.json file, extracts the last step's task_score into
    a top-level field, and creates a DataFrame for evaluation.
    """
    input_file_path = os.path.join(file_path, "out.json")
    result_file_path = os.path.join(file_path, "result.json")

    # Check if out.json exists
    if not os.path.exists(input_file_path):
        logger.error(f"Input file does not exist: {input_file_path}")
        return

    # Load the tasks
    with open(input_file_path, "r") as f:
        all_data = json.load(f)
    logger.info(f"Loaded data from {input_file_path}: {all_data}")

    if not all_data:
        logger.error(f"Input file {input_file_path} is empty.")
        return

    # We'll build a list of dicts, each representing a single task,
    # with a top-level 'task_score' derived from the final step.
    tasks_data = []
    for task in all_data:
        # Safety check: if no steps exist, default to "0 / 1"
        if not task.get("step_list"):
            final_score = "0 / 1"
        else:
            # Grab the last step's score (or default if missing)
            final_score = task["step_list"][-1].get("task_score", "0 / 1")
        
        tasks_data.append({
            "task_id": task.get("task_id", -1),
            "task_name": task.get("task_name", "Unknown"),
            "task_status": task.get("task_status", "unknown"),
            "task_score": final_score,   # <--- put the last step’s task_score up top
            "evaluation": task.get("evaluation", []),
            # You can also store other top-level fields if you want
        })

    # Now we create a DataFrame with 'task_score' at the top level
    df = pd.DataFrame(tasks_data)
    logger.info(f"Data frame created from all_data: {df.head()}")

    # Now 'task_score' is definitely in df.columns!
    if "task_score" not in df.columns:
        logger.error(f"Column 'task_score' missing in data frame: {df.columns}")
        return
    
    # Example: parse step_score or do further processing
    df["step_score"] = df["task_score"].apply(lambda x: float(x.split("/")[0]))
    df["efficiency_score"] = df["step_score"] / df["step_score"].max()  # Example ratio

    # Do anything else you want: computing aggregates, metrics, etc.
    logger.info(f"Final DataFrame for evaluation:\n{df}")

    # If you want, dump results to result.json
    result_dict = df.to_dict(orient="records")
    with open(result_file_path, "w") as json_file:
        json.dump(result_dict, json_file)

    logger.info(f"All results written to {result_file_path}!")



def get_evaluate_result(input_result_path, total_token_cost):
    out_file_path = get_result(input_result_path)
    evaluate(file_path=out_file_path, total_token_cost=total_token_cost)
