import sqlite3, json, yaml

# Load current template from YAML
with open(r'd:\数字分身\backend\personas\default.yaml', 'r', encoding='utf-8') as f:
    yaml_data = yaml.safe_load(f)

conn = sqlite3.connect(r'd:\数字分身\backend\data\digital_twin.db')

# Check existing
row = conn.execute("SELECT config_json, system_prompt_template FROM personas WHERE slug='default'").fetchone()
if row:
    config = json.loads(row[0])
    old_template = row[1]
    new_template = yaml_data['system_prompt_template']

    has_old = 'knowledge_context' in old_template
    has_new = 'knowledge_context' in new_template

    print(f"Old template has knowledge_context: {has_old}")
    print(f"New template has knowledge_context: {has_new}")

    if has_new and not has_old:
        conn.execute("UPDATE personas SET system_prompt_template=? WHERE slug='default'", (new_template,))
        # Also update config with any new values from YAML
        for key in ['max_response_length', 'temperature']:
            if key in yaml_data.get('config', {}):
                config[key] = yaml_data['config'][key]
        conn.execute("UPDATE personas SET config_json=? WHERE slug='default'", (json.dumps(config, ensure_ascii=False),))
        conn.commit()
        print("Updated persona template and config!")
    else:
        print("No update needed")

conn.close()
