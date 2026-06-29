"""
Граф знаний — совместимый формат с MCP memory server.
Файл: knowledge_graph.jsonl (одна JSON-строка на сущность/связь)
"""
import json
import re
import datetime
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class KGEntity:
    name: str
    entity_type: str
    observations: list[str] = field(default_factory=list)


@dataclass
class KGRelation:
    from_entity: str
    to_entity: str
    relation_type: str


class MemoryGraph:
    def __init__(self, path: Path):
        self.path = path
        self.entities: dict[str, KGEntity] = {}
        self.relations: list[KGRelation] = []
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        with open(self.path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get('type') == 'entity':
                    e = KGEntity(obj['name'], obj['entityType'], obj.get('observations', []))
                    self.entities[e.name] = e
                elif obj.get('type') == 'relation':
                    r = KGRelation(obj['from'], obj['to'], obj['relationType'])
                    self.relations.append(r)

    def _save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            for e in self.entities.values():
                f.write(json.dumps({
                    'type': 'entity',
                    'name': e.name,
                    'entityType': e.entity_type,
                    'observations': e.observations,
                }, ensure_ascii=False) + '\n')
            for r in self.relations:
                f.write(json.dumps({
                    'type': 'relation',
                    'from': r.from_entity,
                    'to': r.to_entity,
                    'relationType': r.relation_type,
                }, ensure_ascii=False) + '\n')

    # ──── Запись ────

    def upsert_entity(self, name: str, entity_type: str, observations: list[str] | None = None) -> KGEntity:
        if name not in self.entities:
            self.entities[name] = KGEntity(name, entity_type, [])
        if observations:
            existing = set(self.entities[name].observations)
            self.entities[name].observations.extend(o for o in observations if o not in existing)
        self._save()
        return self.entities[name]

    def add_observation(self, entity_name: str, entity_type: str, observation: str):
        self.upsert_entity(entity_name, entity_type)
        if observation not in self.entities[entity_name].observations:
            self.entities[entity_name].observations.append(observation)
            self._save()

    def add_relation(self, from_e: str, to_e: str, rel_type: str):
        for r in self.relations:
            if r.from_entity == from_e and r.to_entity == to_e and r.relation_type == rel_type:
                return
        self.relations.append(KGRelation(from_e, to_e, rel_type))
        self._save()

    # ──── Чтение ────

    def get_user_context(self, chat_id: int) -> str:
        """Возвращает структурированный контекст пользователя для промпта."""
        user_key = f"user_{chat_id}"
        lines = []

        if user_key in self.entities:
            e = self.entities[user_key]
            lines.append(f"Пользователь (id={chat_id}):")
            for obs in e.observations[-20:]:
                lines.append(f"  • {obs}")

        for r in self.relations:
            if r.from_entity == user_key and r.to_entity in self.entities:
                related = self.entities[r.to_entity]
                lines.append(f"\n  [{r.relation_type}] → {r.to_entity} ({related.entity_type}):")
                for obs in related.observations[-5:]:
                    lines.append(f"    • {obs}")

        return "\n".join(lines) if lines else ""

    # ──── Автоизвлечение фактов ────

    def save_from_session(self, chat_id: int, user_message: str, assistant_message: str):
        """
        Извлекает структурированные факты из коуч-диалога без дополнительного вызова LLM.
        Эвристика: цели с числами, обязательства, энергодренажи.
        """
        user_key = f"user_{chat_id}"
        self.upsert_entity(user_key, 'person')
        today = datetime.date.today().isoformat()

        # Числовые цели (200к, 200 000 ₽, 5 млн и т.д.)
        for m in re.findall(
            r'(\d[\d\s]*(?:к\b|тыс\.?|000|млн)[^\n.!?]{0,60})',
            user_message, re.IGNORECASE
        )[:3]:
            goal_name = f"цель_{re.sub(r'[^а-яёa-z0-9]', '_', m[:40].strip().lower(), flags=re.I)}"
            self.upsert_entity(goal_name, 'goal', [m.strip()])
            self.add_relation(user_key, goal_name, 'стремится_к')

        # Обязательства («я буду», «начну», «сделаю», «обязуюсь»)
        for m in re.findall(
            r'(?:я буду|обязуюсь|сделаю|планирую|начну|берусь)\s+(.{10,120}?)(?:[.!?\n]|$)',
            user_message, re.IGNORECASE
        )[:2]:
            self.add_observation(user_key, 'person', f"[{today}] Обязательство: {m.strip()}")

        # Энергодренажи («терплю», «надоело», «бесит»)
        for m in re.findall(
            r'(?:терплю|вынужден терпеть|надоело|достало|бесит)\s+(.{5,100}?)(?:[.!?\n]|$)',
            user_message, re.IGNORECASE
        )[:3]:
            drain_name = f"drain_{re.sub(r'[^а-яёa-z0-9]', '_', m[:30].strip().lower(), flags=re.I)}"
            self.upsert_entity(drain_name, 'toleration', [m.strip()])
            self.add_relation(user_key, drain_name, 'терпит')

        # Краткая суть сообщения (всегда, если достаточно длинное)
        if len(user_message) > 40:
            short = user_message[:180].strip().replace('\n', ' ')
            self.add_observation(user_key, 'person', f"[{today}] {short}")
