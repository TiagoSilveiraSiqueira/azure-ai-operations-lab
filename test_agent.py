"""Testes locais: não conectam Ollama, Azure ou qualquer serviço externo."""

import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.request import ProxyHandler, Request

import agent


class DemoTests(unittest.TestCase):
    def test_three_scenarios_have_expected_symptom_categories(self):
        expected = {"INC-001": "latencia", "INC-002": "pressao-memoria",
                    "INC-003": "lacuna-observabilidade"}
        for incident_id, category in expected.items():
            with self.subTest(incident=incident_id):
                result = agent.triage(agent.INCIDENTS[incident_id])
                self.assertEqual(result["assessment"]["category"], category)
                self.assertFalse(result["uses_llm"])
                self.assertIsNone(result["fallback"])

    def test_demo_does_not_call_a_model(self):
        with patch("agent.request_ollama") as request:
            agent.triage(agent.INCIDENTS["INC-001"])
        request.assert_not_called()

    def test_a_value_within_target_does_not_prove_latency_problem(self):
        incident = copy.deepcopy(agent.INCIDENTS["INC-001"])
        incident["evidence"][0]["value"] = 320
        self.assertEqual(agent.demo_assessment(incident)["category"], "indeterminado")

    def test_next_steps_are_separate_from_model_generated_text(self):
        incident = agent.INCIDENTS["INC-001"]
        assessment = agent.demo_assessment(incident)
        assessment["hypotheses"] = ["Texto ilustrativo do modelo para revisão."]
        with patch("agent.request_ollama", return_value=assessment):
            result = agent.triage(incident, "ollama")
        self.assertTrue(result["uses_llm"])
        self.assertEqual(result["next_steps"], agent.NEXT_STEPS["latencia"])


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.incident = agent.INCIDENTS["INC-001"]
        self.assessment = agent.demo_assessment(self.incident)

    def test_valid_assessment_round_trip(self):
        value = json.loads(json.dumps(self.assessment))
        self.assertEqual(agent.validate_assessment(value, self.incident), self.assessment)

    def test_unknown_evidence_id_is_rejected(self):
        self.assessment["evidence_ids"].append("E-999")
        with self.assertRaises(ValueError):
            agent.validate_assessment(self.assessment, self.incident)

    def test_evidence_from_another_incident_is_rejected(self):
        self.assessment["evidence_ids"] = ["E-201"]
        with self.assertRaises(ValueError):
            agent.validate_assessment(self.assessment, self.incident)

    def test_empty_or_duplicate_evidence_ids_are_rejected(self):
        for ids in ([], ["E-101", "E-101"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.assessment["evidence_ids"] = ids
                agent.validate_assessment(self.assessment, self.incident)

    def test_category_must_be_supported_and_reference_relevant_metric(self):
        for category, ids in (("reinicio", ["E-101"]), ("pressao-memoria", ["E-101"]),
                              ("latencia", ["E-102"])):
            with self.subTest(category=category, ids=ids), self.assertRaises(ValueError):
                self.assessment["category"] = category
                self.assessment["evidence_ids"] = ids
                agent.validate_assessment(self.assessment, self.incident)

    def test_extra_tool_or_command_fields_are_rejected(self):
        self.assessment["command"] = "campo ilustrativo não permitido"
        with self.assertRaises(ValueError):
            agent.validate_assessment(self.assessment, self.incident)

    def test_category_requires_the_cited_metric_to_exceed_its_target(self):
        incident = copy.deepcopy(self.incident)
        incident["evidence"][1] = {"id": "E-102", "metric": "latency_p95_ms",
                                   "value": 320, "target_max": 400}
        self.assessment["evidence_ids"] = ["E-102"]
        with self.assertRaises(ValueError):
            agent.validate_assessment(self.assessment, incident)

    def test_invalid_text_shapes_are_rejected(self):
        for field, value in (("summary", ""), ("summary", "x" * 801),
                             ("questions", "texto"), ("hypotheses", [42])):
            with self.subTest(field=field, value=str(value)[:20]), self.assertRaises(ValueError):
                assessment = copy.deepcopy(agent.demo_assessment(self.incident))
                assessment[field] = value
                agent.validate_assessment(assessment, self.incident)

    def test_model_text_with_invalid_unicode_is_rejected(self):
        self.assessment["summary"] = "\ud800"
        with self.assertRaises(ValueError):
            agent.validate_assessment(self.assessment, self.incident)


class LocalModelTests(unittest.TestCase):
    def test_model_unavailable_falls_back_with_clear_status(self):
        with patch("agent.request_ollama", side_effect=URLError("erro local ilustrativo")):
            result = agent.triage(agent.INCIDENTS["INC-001"], "ollama")
        self.assertEqual(result["mode_requested"], "ollama")
        self.assertEqual(result["mode_used"], "demo")
        self.assertFalse(result["uses_llm"])
        self.assertIn("regras", result["fallback"])
        self.assertNotIn("erro local ilustrativo", result["fallback"])

    def test_invalid_model_response_falls_back(self):
        with patch("agent.request_ollama", return_value={"category": "latencia"}):
            result = agent.triage(agent.INCIDENTS["INC-001"], "ollama")
        self.assertEqual(result["mode_used"], "demo")
        self.assertIsNotNone(result["fallback"])

    def test_json_decoding_error_falls_back(self):
        with patch("agent.request_ollama", side_effect=json.JSONDecodeError("bad", "", 0)):
            result = agent.triage(agent.INCIDENTS["INC-002"], "ollama")
        self.assertEqual(result["assessment"]["category"], "pressao-memoria")
        self.assertFalse(result["uses_llm"])

    def test_local_request_is_fixed_and_contains_only_synthetic_incident(self):
        incident = agent.INCIDENTS["INC-001"]
        envelope = {"response": json.dumps(agent.demo_assessment(incident))}
        response = MagicMock()
        response.read.return_value = json.dumps(envelope).encode("utf-8")
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch("agent.build_local_opener", return_value=opener):
            result = agent.request_ollama(incident, agent.DEFAULT_MODEL)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/generate")
        self.assertEqual(request.get_method(), "POST")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(json.loads(json.loads(request.data)["prompt"]), incident)
        self.assertEqual(result["category"], "latencia")

    def test_local_opener_does_not_use_environment_proxies(self):
        with patch("agent.build_opener", return_value="mock-opener") as factory:
            self.assertEqual(agent.build_local_opener(), "mock-opener")
        proxy, redirect = factory.call_args.args
        self.assertIsInstance(proxy, ProxyHandler)
        self.assertEqual(proxy.proxies, {})
        self.assertIsInstance(redirect, agent.NoRedirects)

    def test_redirects_are_blocked_before_remote_request(self):
        handler = agent.NoRedirects()
        request = Request(agent.OLLAMA_URL)
        with self.assertRaises(URLError):
            handler.redirect_request(request, None, 302, "redirect", {}, "https://example.com")

    def test_invalid_model_name_is_rejected_without_request(self):
        with patch("agent.build_local_opener") as factory, self.assertRaises(ValueError):
            agent.request_ollama(agent.INCIDENTS["INC-001"], "nome com espaços")
        factory.assert_not_called()

    def test_cloud_model_names_are_blocked_before_request_and_use_explicit_fallback(self):
        incident = agent.INCIDENTS["INC-001"]
        for model in ("gpt-oss:120b-cloud", "gemini-3-flash-preview:cloud", "modelo:Cloud"):
            with self.subTest(model=model), patch("agent.build_local_opener") as factory:
                with self.assertRaises(agent.CloudModelNotAllowed):
                    agent.request_ollama(incident, model)
                result = agent.triage(incident, mode="ollama", model=model)
                factory.assert_not_called()
                self.assertEqual(result["mode_requested"], "ollama")
                self.assertEqual(result["mode_used"], "demo")
                self.assertFalse(result["uses_llm"])
                self.assertIn("cloud bloqueado", result["fallback"])
                self.assertIn("sem enviar o incidente", result["fallback"])

    def test_response_size_limit_is_enforced(self):
        response = MagicMock()
        response.read.return_value = b"x" * (agent.MAX_RESPONSE_BYTES + 1)
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch("agent.build_local_opener", return_value=opener), self.assertRaises(ValueError):
            agent.request_ollama(agent.INCIDENTS["INC-001"], agent.DEFAULT_MODEL)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.document = {"incidents": copy.deepcopy(list(agent.INCIDENTS.values()))}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "incidents.json"

    def write_document(self, document=None):
        self.path.write_text(json.dumps(document or self.document), encoding="utf-8")
        return str(self.path)

    def test_example_is_valid_and_matches_embedded_scenarios(self):
        example = Path(__file__).parent / "incidents.example.json"
        self.assertEqual(agent.load_incidents(example), agent.INCIDENTS)

    def test_public_cases_validate_without_metrics_and_preserve_evidence_references(self):
        example = Path(__file__).parent / "incidents.public.example.json"
        incidents = agent.load_incidents(example)
        self.assertEqual(len(incidents), 2)
        with patch("agent.request_ollama") as model:
            for incident in incidents.values():
                with self.subTest(incident=incident["id"]):
                    self.assertTrue(incident["evidence"])
                    for evidence in incident["evidence"]:
                        self.assertEqual(set(evidence), {"id", "observation"})
                    result = agent.triage(incident)
                    self.assertEqual(result["assessment"]["category"], "indeterminado")
                    self.assertEqual(set(result["assessment"]["evidence_ids"]),
                                     {evidence["id"] for evidence in incident["evidence"]})
                    self.assertFalse(result["uses_llm"])
        model.assert_not_called()

    def test_local_input_loads_and_uses_custom_threshold(self):
        self.document["incidents"][0]["evidence"][0]["target_max"] = 900
        incidents = agent.load_incidents(self.write_document())
        result = agent.triage(incidents["INC-001"])
        self.assertEqual(result["assessment"]["category"], "indeterminado")

    def test_input_size_limit_is_checked_before_parsing(self):
        self.path.write_bytes(b"x" * (agent.MAX_INPUT_BYTES + 1))
        with self.assertRaisesRegex(agent.InputError, "64 KiB"):
            agent.load_incidents(self.path)

    def test_incident_and_evidence_count_limits(self):
        for mutate in (
            lambda value: value.update(incidents=[]),
            lambda value: value.update(incidents=[value["incidents"][0]] * 21),
            lambda value: value["incidents"][0].update(evidence=[]),
            lambda value: value["incidents"][0].update(evidence=[value["incidents"][0]["evidence"][0]] * 11),
        ):
            document = copy.deepcopy(self.document)
            mutate(document)
            with self.assertRaises(agent.InputError):
                agent.validate_incidents(document)

    def test_duplicate_ids_are_rejected(self):
        for level in ("incident", "evidence"):
            document = copy.deepcopy(self.document)
            if level == "incident":
                document["incidents"][1]["id"] = "INC-001"
            else:
                document["incidents"][1]["evidence"][0]["id"] = "E-101"
            with self.subTest(level=level), self.assertRaises(agent.InputError):
                agent.validate_incidents(document)

    def test_extra_fields_are_rejected_without_following_references(self):
        self.document["incidents"][0]["read_path"] = "outro-arquivo-ficticio.json"
        path = self.write_document()
        original_open = Path.open
        opened = []

        def record_open(selected, *args, **kwargs):
            opened.append(str(selected))
            return original_open(selected, *args, **kwargs)

        with patch.object(Path, "open", new=record_open), self.assertRaises(agent.InputError):
            agent.load_incidents(path)
        self.assertEqual(opened, [path])

    def test_wrong_types_ranges_and_unknown_metrics_are_rejected(self):
        for field, value in (("value", True), ("value", -1), ("value", 3_600_001),
                             ("target_max", "400"), ("metric", "metrica-nao-suportada")):
            document = copy.deepcopy(self.document)
            document["incidents"][0]["evidence"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(agent.InputError):
                agent.validate_incidents(document)

    def test_percentages_queue_counts_and_boolean_types_are_checked(self):
        for incident, evidence, value in ((0, 1, 101), (1, 0, 101), (1, 1, 1.5), (2, 0, 0)):
            document = copy.deepcopy(self.document)
            document["incidents"][incident]["evidence"][evidence]["value"] = value
            with self.subTest(incident=incident, evidence=evidence), self.assertRaises(agent.InputError):
                agent.validate_incidents(document)

    def test_missing_required_fields_and_oversized_text_are_rejected(self):
        document = copy.deepcopy(self.document)
        del document["incidents"][0]["window"]
        with self.assertRaises(agent.InputError):
            agent.validate_incidents(document)
        document = copy.deepcopy(self.document)
        document["incidents"][0]["service"] = "x" * 121
        with self.assertRaises(agent.InputError):
            agent.validate_incidents(document)

    def test_duplicate_json_fields_and_nonfinite_numbers_are_rejected(self):
        for text in ('{"incidents": [], "incidents": []}',
                     json.dumps(self.document).replace('820', 'NaN', 1)):
            self.path.write_text(text, encoding="utf-8")
            with self.subTest(text=text[:25]), self.assertRaises(agent.InputError):
                agent.load_incidents(self.path)

    def test_invalid_json_utf8_and_missing_file_have_clear_errors(self):
        for body in (b"not-json", b"\xff\xfe"):
            self.path.write_bytes(body)
            with self.subTest(body=body), self.assertRaisesRegex(agent.InputError, "JSON"):
                agent.load_incidents(self.path)
        with self.assertRaisesRegex(agent.InputError, "ler o arquivo"):
            agent.load_incidents(Path(self.temp.name) / "arquivo-inexistente.json")

    def test_escaped_invalid_unicode_is_rejected_before_output(self):
        self.document["incidents"][0]["service"] = "\ud800"
        with self.assertRaisesRegex(agent.InputError, "Unicode"):
            agent.load_incidents(self.write_document())

    def test_cli_input_selects_incident_and_list_without_model(self):
        path = self.write_document()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("agent.request_ollama") as model:
            self.assertEqual(agent.main(["--input", path, "--incident", "INC-002"]), 0)
        model.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["assessment"]["category"], "pressao-memoria")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            agent.main(["--input", path, "--list"])
        self.assertEqual(len(json.loads(output.getvalue())), 3)

    def test_cli_defaults_to_first_record_in_input(self):
        self.document["incidents"] = [self.document["incidents"][2]]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            agent.main(["--input", self.write_document()])
        self.assertEqual(json.loads(output.getvalue())["incident_id"], "INC-003")

    def test_cli_invalid_input_does_not_echo_values_or_traceback(self):
        marker = "VALOR_FICTICIO_NAO_EXIBIR"
        self.document["incidents"][0]["evidence"][0]["value"] = marker
        path = self.write_document()
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                agent.main(["--input", path])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Erro de entrada", stderr.getvalue())
        self.assertNotIn(marker, stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_unknown_incident_error_does_not_echo_argument(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            agent.main(["--input", self.write_document(), "--incident", "ID_FICTICIO_NAO_EXIBIR"])
        self.assertEqual(raised.exception.code, 2)
        self.assertNotIn("ID_FICTICIO_NAO_EXIBIR", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
