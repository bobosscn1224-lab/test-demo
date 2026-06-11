"""Update persona template AND config directly via sqlite3."""
import sqlite3
import json
import yaml

yaml_path = r'd:\数字分身\backend\personas\default.yaml'
db_path = r'd:\数字分身\backend\data\digital_twin.db'

with open(yaml_path, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

new_template = data['system_prompt_template']
new_config = data.get('config', {})
new_config_json = json.dumps(new_config, ensure_ascii=False)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Update system_prompt_template
c.execute("UPDATE personas SET system_prompt_template = ? WHERE slug = 'default'", (new_template,))
print(f'system_prompt_template rows updated: {c.rowcount}')

# Update config_json
c.execute("UPDATE personas SET config_json = ? WHERE slug = 'default'", (new_config_json,))
print(f'config_json rows updated: {c.rowcount}')

conn.commit()

c.execute("SELECT slug, length(system_prompt_template), config_json FROM personas WHERE slug='default'")
row = c.fetchone()
if row:
    print(f'  slug={row[0]}, template_len={row[1]}')
    config = json.loads(row[2]) if row[2] else {}
    print(f'  max_response_length={config.get("max_response_length", "N/A")}')
    print(f'  temperature={config.get("temperature", "N/A")}')
else:
    print('  No persona found — will seed on next startup')
conn.close()
