import subprocess
import sys
import os
import argparse
import requests
import re
from typing import List, Dict, Callable

class LogLevel:
    DEBUG = 0
    VERBOSE = 1
    INFO = 2
    ERROR = 3

default_log_level = LogLevel.INFO
def get_git_diff_staged():
    # 获取 git diff --staged 输出
    result = subprocess.run(['git', 'diff', '--staged'], capture_output=True, text=True)
    return result.returncode, result.stdout

def get_git_last_diff():
    # 获取 git diff HEAD HEAD~1 输出
    result = subprocess.run(['git', 'diff', 'HEAD~1', 'HEAD'], capture_output=True, text=True)
    return result.returncode, result.stdout

def git_add_all():
    result = subprocess.run(['git', 'add', '.'], capture_output=True, text=True)
    return result.returncode, result.stdout

def git_status():
    result = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
    return result.returncode, result.stdout

def git_commit(message, *argv):
    result = subprocess.run(['git', 'commit', *argv, '-m', message], capture_output=True, text=True)
    return result.returncode, result.stdout

def extract_xml(text: str, tag: str) -> str:
    """
    Extracts the content of the specified XML tag from the given text. Used for parsing structured responses 

    Args:
        text (str): The text containing the XML.
        tag (str): The XML tag to extract content from.

    Returns:
        str: The content of the specified XML tag, or an empty string if the tag is not found.
    """
    match = re.search(f'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    return match.group(1) if match else ""

def system_summary_prompt():
    prompt = f"""
    ## Role
    你是一名程序员，用户会提供一个 git diff 的输出，你需要根据这个输出生成一份详尽的代码变更说明，不超过1000字。

    ## Requirements
    提交日志应该满足以下要求：
    - 描述清楚功能修改的内容、性质及其目的
    - 尽量使用中文，专业词汇除外
    - 不要带上任何文件名等其他信息

    ## Locale
    - zh-cn
    """
    return prompt

def system_classify_prompt(routes: Dict[str, str]):
    prompt = f"""
    ## Role
    You are a classifier. Users will provide a code change description, and you need to determine which type of commit it belongs to based on this description.
    其中feature表示功能修改；
    fix表示bug修复；
    optimize表示性能优化；
    doc表示文档修改或新增；
    log表示添加日志或者调试信息打印；
    comment表示添加注释，其内容明确以#或者//或者///或者/*开头。
    Analyze the input and select the most appropriate type from these options: {list(routes.keys())}.
    
    <reasoning>
    简要介绍为何这段代码变更属于这种commit类型。
    </reasoning>

    <type>
    The chosen type name
    </type>
    """
    return prompt


def regenerate_system_prompt(router_hint: str):
    prompt = f"""
    ## Role
    你是一位 Git 提交日志助手，你需要根据用户输入的修改信息总结归纳生成一个简洁明了的提交日志，字数控制在 150 字以内,
    用于输入的修改信息属于{router_hint}类型，请根据此类型进行总结归纳。

    ## Requirements
    提交日志应该满足以下要求：
    - 简洁明了，不要冗余，描述清楚功能修改及其目的
    - 尽量使用中文，专业词汇除外
    - 使用现在时
    - 使用祈使语气
    - 保持提交信息头部简洁，不要带上任何文件名等其他信息

    以下是一些示例：

    ## Examples
    ```
    - 添加了某处日志
    - 添加了某个功能
    - 修复了某个bug
    - 优化了某个场景下的性能
    - 更新了某个文档
    - 添加了某处注释
    ```

    ## Locale
    - zh-cn
    """
    return prompt

def log(message, level=LogLevel.INFO):
    if level >= default_log_level:
        print(f"{message}")

def llm_call(system_content, user_content, ollama_model):
    """
    调用 LLM API 获取响应
    Args:
        system_content: system prompt
        user_content: user input
        ollama_model: model name
    Returns:
        str: LLM response message
    """
    ollama_url = "http://localhost:11434"
    try:
        response = requests.post(f"{ollama_url}/api/chat", json={
            "model": ollama_model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            "stream": False
        })
        response.raise_for_status()
        response_json = response.json()
        response_message = response_json["message"]["content"]
        return response_message.replace("```", "")
    except requests.exceptions.RequestException as e:
        log(f"Failed to call LLM API: {str(e)}", LogLevel.ERROR)
        sys.exit(1)

def strip_leading_dash(text: str) -> str:
    """
    Remove leading dash/hyphen from a string
    
    Args:
        text (str): Input string that may start with dash
        
    Returns:
        str: String with leading dash removed and whitespace stripped
    """
    return text.lstrip('- ').strip()

# args: 
# -m commit: message
# -a add: add all files to git
# -v --verbose: log level, default is INFO
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI assistant for git commit")
    parser.add_argument("-m", "--message", required=False, help="The commit message")
    parser.add_argument("-a", "--add", action="store_true", help="Add all files to git")
    parser.add_argument("--amend", action="store_true", help="Amend the last commit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log level, default is INFO")
    args = parser.parse_args()

    AC_OLLAMA_URL = os.getenv("AC_OLLAMA_URL", "http://localhost:11434")
    AC_OLLAMA_MODEL = os.getenv("AC_OLLAMA_MODEL", "qwen2.5-coder:14b")

    if args.verbose:
        default_log_level = LogLevel.DEBUG
    else:
        default_log_level = LogLevel.INFO

    message = args.message
    log(f"Your commit message: {message}", LogLevel.VERBOSE)
    
    if args.add:
        log("AI assistant for git commit, now start adding all files...", LogLevel.INFO)
        return_code, _ = git_add_all()
        if return_code != 0:
            log("Failed to add all files", LogLevel.ERROR)
            sys.exit(1)
        log("Done!\n", LogLevel.INFO)

    log("Now we will get the git status...", LogLevel.INFO)
    return_code, files = git_status()
    if return_code != 0:
        log("Failed to get git status", LogLevel.ERROR)
        sys.exit(1)
    
    if not args.amend:
        if files is None or len(files) == 0:
            log("No files to commit, we will exit now...", LogLevel.INFO)
            sys.exit(0)
      
    log(f"We will commit the following files: \n{files}", LogLevel.INFO)
    
    log("Now we will generate the diff messages...", LogLevel.INFO)
    return_code, diff_message = get_git_diff_staged()
    if return_code != 0:
        log("Failed to get git diff", LogLevel.ERROR)
        sys.exit(1)
    log(f"Diff message: {diff_message}", LogLevel.VERBOSE)
    log("Done!\n", LogLevel.INFO)

    last_diff_message = ""
    if args.amend:
        log("Now we will amend the last commit...", LogLevel.INFO)
        return_code, last_diff_message = get_git_last_diff()
        if return_code != 0:
            log("Failed to amend the last commit", LogLevel.ERROR)
            sys.exit(1)
        else:
            log(f"Last diff message: {last_diff_message}", LogLevel.DEBUG)

    user_content = f'''
    User message:
    {message or ""}
    Files:
    {files}
    Diff:
    {diff_message or ""}
    {last_diff_message or ""}
    '''

    # use ollama to generate the summary message
    # 打印user message
    log(f"User message: {user_content}", LogLevel.INFO)
    log("Now we will generate the summary message using ollama...", LogLevel.INFO)
    detail_summary = llm_call(
        system_summary_prompt(),
        user_content,
        AC_OLLAMA_MODEL
    )

    log(f"Now we got the summary:Response message: {detail_summary}", LogLevel.INFO)

    support_routes = {
    "feature": "功能修改",
    "fix": "bug修复",
    "optimize": "性能优化",
    "doc": "文档修改或新增",
    "log": "添加日志",
    "comment": "添加注释",
    }

    # use ollama to classify the commit message type 
    log("Now we will classify the commit message using ollama...", LogLevel.INFO)
    route_msg = llm_call(
        system_classify_prompt(support_routes),
        detail_summary,
        AC_OLLAMA_MODEL
    )

    reasoning = extract_xml(route_msg, 'reasoning')
    route_type = extract_xml(route_msg, 'type').strip().lower()
    print(f"\nSelected route: {route_type}")
    
    # Process input with selected specialized prompt
    router_hint = support_routes[route_type]
    
    log(f"Now we got the commit message type: {route_msg}", LogLevel.INFO)  

    # 根据代码变更的类型，对上一步的输出进一步处理。
    regen_summary = llm_call(
        regenerate_system_prompt(router_hint),
        detail_summary,
        AC_OLLAMA_MODEL
    )
    final_msg = route_type + ':' + strip_leading_dash(regen_summary)

    # # If message is too long, re-generate it and make it shorter.
    # if len(response_message) > 200:
    #     log(f"Response message: {response_message}", LogLevel.VERBOSE)
    #     log("Message is too long, we will shorten it...", LogLevel.INFO)
    #     response_message = llm_call(
    #         regenerate_system_prompt(),
    #         response_message,
    #         AC_OLLAMA_MODEL
    #     )

    # log(f"Response message: {response_message}", LogLevel.VERBOSE)
    # log("Done!\n", LogLevel.INFO)

    if message is not None and len(message) > 0:
        commit_message = message + "\n" + final_msg
    else:
        commit_message = final_msg
    commit_message = commit_message.strip()
    log(f"Commit message: {commit_message}", LogLevel.INFO)
    log("Now commit to git...", LogLevel.INFO)
    if args.amend:
        return_code, _ = git_commit(commit_message, '--amend')
    else:
        return_code, _ = git_commit(commit_message)
    if return_code != 0:
        log("Failed to commit", LogLevel.ERROR)
        sys.exit(1)
    log("Done!\n", LogLevel.INFO)
    log("Thank you for using AI assistant for git commit!", LogLevel.INFO)
