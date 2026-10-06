import json
import tempfile
import unittest
from pathlib import Path

from multi_agent import (
    build_controller_review_request,
    controller_review_prompt,
    format_controller_report,
    needs_controller_review,
    project_workflow_prompt,
    WorkflowState,
)


class ControllerReviewTests(unittest.TestCase):
    def test_runs_for_actionable_project_work(self):
        self.assertTrue(needs_controller_review("Запусти", "изменить систему Гаврика"))
        self.assertTrue(needs_controller_review("Поправь", "репозиторий бота"))

    def test_skips_general_questions(self):
        self.assertFalse(needs_controller_review("Что делает контролёр системы?"))
        self.assertFalse(needs_controller_review("Найди авиабилеты", "проект отпуск"))

    def test_old_project_history_does_not_trigger_on_unrelated_question(self):
        self.assertFalse(needs_controller_review(
            "Что такое контролёр?",
            "Исправь код системы Гаврика",
        ))

    def test_ui_requests_include_design_and_copy_phases(self):
        prompt = project_workflow_prompt("Добавь кнопку настройки")
        self.assertIn("Дизайнер", prompt)
        self.assertIn("Копирайтер", prompt)
        self.assertIn("остановись после Challenger", prompt)
        self.assertNotIn("Дизайнер", project_workflow_prompt("Проверь расчёт"))

    def test_workflow_events_are_compact_and_do_not_store_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = WorkflowState(Path(tmp) / "workflow_state.json")
            state.record_event(
                "controller_pass_completed",
                run_id="abc123",
                role="controller",
                status="pass",
                prompt="secret chat content",
            )
            saved = json.loads((Path(tmp) / "workflow_state.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["events"][0]["status"], "pass")
            self.assertNotIn("secret chat content", json.dumps(saved, ensure_ascii=False))
            self.assertNotIn("prompt", saved["events"][0])

    def test_controller_requires_evidence(self):
        raw = json.dumps({
            "status": "pass",
            "checked": [],
            "findings": [],
            "next_action": "continue",
        })
        self.assertTrue(format_controller_report(raw).startswith("Заблокировано"))

    def test_builds_role_phases_in_declared_order(self):
        prompt = project_workflow_prompt()
        ordered = ["Планировщик", "Архитектор", "Адверсарий", "Разработчик",
                   "Ревьюер", "Тестировщик QA", "Security Auditor",
                   "UX Тестировщик", "Инженер по целостности"]
        positions = [prompt.index(label) for label in ordered]
        self.assertEqual(sorted(positions), positions)
        self.assertIn("последовательные фазы", prompt)
        self.assertIn("не отдельные процессы", prompt)
        self.assertIn("Контролёр будет вызван отдельно", prompt)

    def test_controller_is_read_only_and_demands_evidence(self):
        prompt = controller_review_prompt()
        self.assertIn("только на чтение", prompt)
        self.assertIn("не считай описание роли доказательством её запуска", prompt)
        request = build_controller_review_request("запусти систему", "готово")
        self.assertIn("Запрос пользователя:", request)
        self.assertIn("Ответ и выполненные действия", request)

    def test_malformed_report_fails_closed(self):
        self.assertTrue(format_controller_report("not json").startswith("Заблокировано"))

    def test_high_findings_block_even_if_model_says_pass(self):
        raw = json.dumps({
            "status": "pass",
            "checked": ["workflow state"],
            "findings": [{"severity": "high", "message": "нет evidence"}],
            "next_action": "получить evidence",
        }, ensure_ascii=False)
        report = format_controller_report(raw)
        self.assertTrue(report.startswith("Заблокировано"))
        self.assertIn("Замечание [high]", report)

    def test_valid_pass_report_is_rendered(self):
        raw = json.dumps({
            "status": "pass",
            "checked": ["запуск завершён"],
            "findings": [],
            "next_action": "можно продолжать",
        }, ensure_ascii=False)
        report = format_controller_report(raw)
        self.assertTrue(report.startswith("Проверка пройдена"))
        self.assertIn("Проверено: запуск завершён", report)


if __name__ == "__main__":
    unittest.main()
