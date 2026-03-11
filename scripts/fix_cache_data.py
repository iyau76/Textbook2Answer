import json
import os
import glob

def restore_control_chars(obj):
    if isinstance(obj, str):
        # 恢复被旧版错误解析为控制字符的 LaTeX 指令
        obj = obj.replace('\t', '\\t')
        obj = obj.replace('\b', '\\b')
        obj = obj.replace('\f', '\\f')
        obj = obj.replace('\r', '\\r')
        obj = obj.replace('\n', '\\n')
        return obj
    elif isinstance(obj, list):
        return [restore_control_chars(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: restore_control_chars(v) for k, v in obj.items()}
    return obj

def main():
    print("开始修复可能存在的旧缓存 JSON 控制字符污染...")
    # 查找 output 及可能存在的子目录下的 json
    files = glob.glob("output/**/*.json", recursive=True)
    if not files:
        files = glob.glob("*.json")
        
    for fpath in files:
        if "extracted_tasks.json" in fpath or "solved_answers.json" in fpath:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                continue
                
            fixed = restore_control_chars(data)
            
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(fixed, f, ensure_ascii=False, indent=2)
            print(f"✅ 成功修复文件缓存中可能被吞没的字符: {fpath}")

if __name__ == "__main__":
    main()
