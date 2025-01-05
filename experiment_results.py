import pandas as pd
from pandas import json_normalize
import json
import re
import os
from logs import logger

def parse_thought_action(dict_str):
    thought_action = {}
    thought_match = re.search(r"'thought':\s*(.+?)\s*,\s*'action'", dict_str)
    action_match = re.search(r"'action':\s*(.+?)\s*}", dict_str)
    thought = thought_match.group(1) if thought_match else None
    if thought:
        thought = thought.replace("\\", "").replace("\"", "").replace("\'", "").strip()
    action = action_match.group(1) if action_match else None
    if action:
        action = action.replace("\\", "").replace("\"", "").replace("\'", "").strip()
    thought_action = {"thought": thought, "action": action}
    return thought_action

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
    action_dict = {str(value): name for name, value in action_types if name.isupper()}
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
    extracted_fields["action_type"] = action_dict.get(str(extracted_fields.get("action_type")), "none").lower()
    extracted_fields["fill_text"] = extracted_fields.get("fill_text", "")
    action = ""
    action_type = extracted_fields.get("action_type", "").lower()
    if "google_search" in action_type:
        action = f"google_search[{extracted_fields['fill_text']}]"
    elif "fill_search" in action_type:
        action = f"fill_search[{extracted_fields.get('element_id', '')},{extracted_fields['fill_text']}]"
    elif "fill_form" in action_type:
        action = f"fill_form[{extracted_fields.get('element_id', '')},{extracted_fields['fill_text']}]"
    elif "select_option" in action_type:
        action = f"select_option[{extracted_fields.get('element_id', '')},{extracted_fields['fill_text']}]"
    elif "goto" in action_type and extracted_fields.get('url'):
        action = f"goto[{extracted_fields['url']}]"
    elif "click" in action_type:
        action = f"click[{extracted_fields.get('element_id', '')}]"
    elif "go_back" in action_type:
        action = f"go_back[{extracted_fields.get('element_id', '')}]"
    elif "none" in action_type:
        action = "None"
    elif "cache_data" in action_type:
        action = f"cache_data[{extracted_fields['fill_text']}]"
    elif "final_answer" in action_type:
        action = f"get_final_answer[{extracted_fields['fill_text']}]"
    else:
        action = "unknown_action"
    return action

def score_rate(score):
    try:
        first, second = score.split("/")
        return float(first.strip()) / float(second.strip())
    except Exception as e:
        logger.error(f"Error parsing score '{score}': {e}")
        return 0.0

def parse_step_reward(dict_str):
    score_description = {}
    score_match = re.search(r"'score':\s*(.+?)\s*,\s*'description'", dict_str)
    description_match = re.search(r"'description':\s*(.+?)\s*}", dict_str)
    score = score_match.group(1) if score_match else None
    if score:
        score = score.replace("\\", "").replace("\"", "").replace("\'", "").strip()
    description = description_match.group(1) if description_match else None
    if description:
        description = description.replace("\\", "").replace("\"", "").replace("\'", "").strip()
    score_description = {"score": score, "description": description}
    logger.debug(f"Parsed step_reward: {score_description}")
    return score_description if score and description else None

def process_step_reward(dict_str):
    if isinstance(dict_str, str):
        if dict_str.lower() == "{}":
            return {}
        elif dict_str.lower() == "finished":
            return {"score": 10, "description": "finished"}
        else:
            return parse_step_reward(dict_str)
    elif isinstance(dict_str, dict):
        return dict_str
    else:
        logger.warning(f"Unexpected type for step_reward: {type(dict_str)}")
        return {}

def write_task_result_to_df(each_task_json_file_path):
    try:
        with open(each_task_json_file_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding failed for {each_task_json_file_path}: {e}")
        return None, None, None, None, pd.DataFrame()
    except Exception as e:
        logger.error(f"Error reading {each_task_json_file_path}: {e}")
        return None, None, None, None, pd.DataFrame()

    step_list = data.get("step_list", [])
    task_name = data.get("task_name", "Unknown Task")
    task_status = data.get("status", "Unknown Status")
    reference_task_length = data.get("reference_task_length", 0)
    evaluate_steps = data.get("evaluate_steps", [])

    logger.debug(f"Processing Task: {task_name}, Status: {task_status}, Steps: {len(step_list)}")

    if not step_list:
        logger.warning(f"No steps found for task {task_name}.")

    # Convert all keys to strings except 'step_index'
    for idx, item in enumerate(step_list):
        for key in item:
            if key != "step_index":
                step_list[idx][key] = str(item[key])

    data_df = json_normalize(step_list, errors='ignore')

    # Debugging: Print DataFrame columns to verify 'step_index' presence
    logger.debug(f"DataFrame Columns after normalization: {data_df.columns.tolist()}")

    return task_name, task_status, reference_task_length, evaluate_steps, data_df

def write_to_json(df):
    if 'step_index' not in df.columns:
        logger.error("'step_index' column is missing from the DataFrame.")
        return []
    
    try:
        df["step_index"] = df["step_index"].apply(lambda x: int(x))
    except Exception as e:
        logger.error(f"Error converting 'step_index' to int: {e}")
        df["step_index"] = df["step_index"].apply(lambda x: -1)  # Assign a default value
    
    df["trace_to_dict"] = df["current_trace"].apply(lambda x: parse_thought_action(x))
    df["action_to_str"] = df["execute_action"].apply(lambda x: to_dict(x))
    df["score_rate"] = df["score"].apply(lambda x: score_rate(x))
    df["step_reward"] = df["step_reward"].apply(lambda x: process_step_reward(x))
    df["selector"] = df["selector"].fillna("None")
    df["match_result"] = df["match_func_result"]
    df["element_value"] = df["element_value"].fillna("None")
    df["error"] = df["error_message"].fillna("None")
    df["step_url"] = df["step_url"].fillna("None")
    
    # Select relevant columns
    df_copy = df[
        [
            "step_index",
            "trace_to_dict",
            "selector",
            "action_to_str",
            "score",
            "score_rate",
            "step_reward",
            "step_url",
            "match_result",
            "element_value",
            "error"
        ]
    ]

    def summary(x):
        dic = {
            "step_index": x["step_index"],
            "trace_description": x["trace_to_dict"] if x["trace_to_dict"] else {},
            "selector": x["selector"] if x["selector"] != "None" else "",
            "element_value": x["element_value"] if x["element_value"] != "None" else "",
            "action": x["action_to_str"] if x["action_to_str"] else "",
            "task_score": x["score"],
            "task_score_rate": x["score_rate"],
            "current_reward_score_description": x["step_reward"],
            "url": x["step_url"],
            "match_result": x["match_result"],
            "error": x["error"] if x["error"] != "None" else ""
        }
        logger.debug(f"Processed step: {dic}")
        return dic

    step_list = []
    df_copy.apply(lambda x: step_list.append(summary(x)), axis=1)
    logger.debug(f"Processed {len(step_list)} steps for JSON output.")
    return step_list

def get_result(input_json_path):
    json_result_path = os.path.join(input_json_path, "json_result")
    out_file_path = os.path.join(input_json_path, "result")
    task_list = []
    
    for _, filename in enumerate(os.listdir(json_result_path)):
        file_path = os.path.join(json_result_path, filename)
        if not os.path.isfile(file_path):
            logger.warning(f"Skipping non-file {file_path}.")
            continue
        
        try:
            task_name, task_status, reference_task_length, evaluate_steps, data_df = write_task_result_to_df(file_path)
            if task_name is None:
                logger.warning(f"Skipping file {file_path} due to previous errors.")
                continue
            
            out_json = {
                "task_id": int(filename.split("_")[0]),
                "task_name": task_name,
                "task_status": task_status,
                "step_list": [],
                "evaluation": evaluate_steps
            }

            if not data_df.empty:
                task_step_list = write_to_json(data_df)
                out_json["step_list"] = task_step_list
                task_list.append(out_json)
            else:
                logger.warning(f"No data to append for task {task_name}.")

        except Exception as e:
            logger.error(f"Failed to process file {file_path}: {e}")

    task_list = sorted(task_list, key=lambda x: x['task_id'])

    if not os.path.exists(out_file_path):
        os.makedirs(out_file_path)
    out_json_file_path = os.path.join(out_file_path, 'out.json')
    try:
        with open(out_json_file_path, 'w') as json_file:
            json.dump(task_list, json_file, indent=4)
        logger.info(f"All task results written to {out_json_file_path}.")
    except Exception as e:
        logger.error(f"Failed to write out.json: {e}")

    return out_file_path

def read_json_result(file_path):
    try:
        with open(file_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding failed for {file_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return []
    
    last_action_result_list = []
    for items in data:
        try:
            data_dic = {}
            data_dic["task_id"] = items["task_id"]
            data_dic["task_name"] = items["task_name"]
            data_dic["status"] = items["task_status"]
            # Ensure step_list is not empty
            if items.get("step_list"):
                data_dic["steps"] = items["step_list"][-1]["step_index"] + 1
                data_dic["task_score"] = items["step_list"][-1]["task_score"]
                data_dic["task_score_rate"] = items["step_list"][-1]["task_score_rate"]
            else:
                data_dic["steps"] = 0
                data_dic["task_score"] = "0/0"
                data_dic["task_score_rate"] = 0.0
            data_dic["reward_count"] = len(items.get("evaluation", []))
            last_action_result_list.append(data_dic)
        except KeyError as e:
            logger.error(f"Missing expected key: {e} in task {items.get('task_id', 'Unknown')}")
            continue
        except Exception as e:
            logger.error(f"Error processing task {items.get('task_id', 'Unknown')}: {e}")
            continue
    return last_action_result_list

def calculate_total_score(scores):
    try:
        molecular_sum = sum(float(x.split('/')[0].strip()) for x in scores)
        denominator_sum = sum(float(x.split('/')[1].strip()) for x in scores)
        final_score = molecular_sum / denominator_sum if denominator_sum != 0 else 0.0
        return final_score
    except Exception as e:
        logger.error(f"Error calculating total score: {e}")
        return 0.0

def evaluate(file_path, total_token_cost):
    input_file_path = os.path.join(file_path, "out.json")
    result_file_path = os.path.join(file_path, "result.json")
    all_data = read_json_result(input_file_path)
    if not all_data:
        logger.warning("No data available for evaluation.")
        return
    
    df = pd.DataFrame(all_data)
    if df.empty:
        logger.warning("DataFrame is empty after reading JSON result.")
        return
    
    try:
        df["step_score"] = df["task_score"].apply(lambda x: float(x.split("/")[0]))
    except Exception as e:
        logger.error(f"Error parsing 'task_score': {e}")
        df["step_score"] = 0.0
    
    df["efficiency_score"] = df.apply(lambda row: row['steps'] / row['step_score'] if row['step_score'] != 0 else 0, axis=1)
    
    df["task_near_success"] = df["task_score"].apply(lambda x: float(x.split("/")[1].strip()) - float(x.split("/")[0].strip()) == 1.0)
    
    df_evaluate = df[["task_name", "status", "steps", "task_score",
                     "task_score_rate", "step_score", "efficiency_score", "task_near_success"]]
    
    key_node_completion_rate = calculate_total_score(df_evaluate['task_score'])
    key_node_completion_sum = df_evaluate['step_score'].sum()
    task_success_rate = df_evaluate[df_evaluate["status"] == "finished"].shape[0] / df_evaluate.shape[0] if df_evaluate.shape[0] > 0 else 0
    task_near_success_rate = df_evaluate[df_evaluate["task_near_success"] == True].shape[0] / df_evaluate.shape[0] if df_evaluate.shape[0] > 0 else 0
    
    average_step_score_rate = df_evaluate["task_score_rate"].mean()
    average_efficiency_score = df_evaluate["efficiency_score"].mean()
    usd_efficiency_score = total_token_cost / key_node_completion_sum if key_node_completion_sum != 0 else 0.0
    
    result_dict = {
        "task_counts": df_evaluate.shape[0],
        "average_step_score_rate": average_step_score_rate,
        "average_efficiency_score": average_efficiency_score,
        "usd_efficiency_score": usd_efficiency_score,
        "key_node_completion_rate": key_node_completion_rate,
        "task_success_rate": task_success_rate,
        "task_near_success_rate": task_near_success_rate
    }
    
    try:
        with open(result_file_path, 'w') as json_file:
            json.dump(result_dict, json_file, indent=4)
        logger.info(f'\033[31mAll results write to {result_file_path}!\033[0m')
    except Exception as e:
        logger.error(f"Failed to write evaluation results: {e}")

def get_evaluate_result(input_result_path, total_token_cost):
    out_file_path = get_result(input_result_path)
    evaluate(file_path=out_file_path, total_token_cost=total_token_cost)
