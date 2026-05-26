import re
import json

def route(text):
    edit_content = None
    comment = None
    
    edit_match = re.search(r"<edit>(.*?)</edit>", text, re.DOTALL | re.IGNORECASE)
    if edit_match:
        edit_content = edit_match.group(1).strip()
        
    comment_match = re.search(r"<comment>(.*?)</comment>", text, re.DOTALL | re.IGNORECASE)
    if comment_match:
        comment = comment_match.group(1).strip()
        
    if not edit_content and not comment:
        edit_open_match = re.search(r"<edit>(.*)", text, re.DOTALL | re.IGNORECASE)
        if edit_open_match:
            edit_content = edit_open_match.group(1).strip()
        else:
            comment_open_match = re.search(r"<comment>(.*)", text, re.DOTALL | re.IGNORECASE)
            if comment_open_match:
                comment = comment_open_match.group(1).strip()
                
    if not edit_match and not comment_match:
        clean = text.strip()
        start_idx = clean.find("{")
        end_idx = clean.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            try:
                data = json.loads(clean[start_idx:end_idx+1])
                edit_content = data.get("edit")
                comment = data.get("comment") or ""
            except Exception:
                pass
                
    if not edit_content and not comment:
        print("RETURN CHAT")
        return

    print("EDIT:", repr(edit_content)[:100])
    print("COMMENT:", repr(comment))

text_trunc = "<edit>\nVoici mon contenu avec { et } au milieu, mais pas fermé !"
route(text_trunc)