"""Rapport d'audit de sécurité — NURU V12 Phase 1, Sprint 8.

Classe:
    AuditReport: Rapport structuré avec findings, severity, statistiques.
    generate_report(): Génération de rapport formaté.

Utilisation:
    report = AuditReport()
    report.add_finding(module="shell_exec.py", check="...", severity="HIGH",
                       status="PASS", description="...")
    print(report.generate_report())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


# ── Severity constants ───────────────────────────────────────────


class SeverityLevel:
    """Niveaux de sévérité normalisés."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    ALL = (CRITICAL, HIGH, MEDIUM, LOW, INFO)

    _order = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4}

    @classmethod
    def sort_key(cls, severity: str) -> int:
        return cls._order.get(severity, 99)


# ── Finding ──────────────────────────────────────────────────────


@dataclass
class Finding:
    """Un finding individuel d'audit.

    Attributes:
        module: Module source du finding (ex: shell_exec.py).
        check: Nom du check effectué.
        severity: Niveau de sévérité (CRITICAL, HIGH, MEDIUM, LOW, INFO).
        status: Statut (PASS, FAIL, FIXED).
        description: Description textuelle du finding.
        recommendation: Recommandation (optionnelle).
    """

    module: str
    check: str
    severity: str
    status: str
    description: str
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── CorrectiveAction ─────────────────────────────────────────────


@dataclass
class CorrectiveAction:
    """Action corrective appliquée.

    Attributes:
        module: Module modifié.
        description: Description du correctif.
        files: Liste des fichiers modifiés.
    """

    module: str
    description: str
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── AuditReport ──────────────────────────────────────────────────


class AuditReport:
    """Rapport d'audit de sécurité structuré.

    Collecte les findings, génère des statistiques et produit
    un rapport textuel ou JSON.

    Utilisation:
        report = AuditReport()
        report.add_finding(...)
        report.add_corrective_action(...)
        text = report.generate_report()
    """

    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.corrective_actions: list[CorrectiveAction] = []
        self.timestamp: str = datetime.now().isoformat()
        self.audit_title: str = "Audit Sécurité Sprint 8 — NURU V12 Phase 1"

    # ── Ajout de findings ─────────────────────────────────────

    def add_finding(
        self,
        module: str,
        check: str,
        severity: str,
        status: str,
        description: str,
        recommendation: str = "",
    ) -> None:
        """Ajoute un finding à l'audit.

        Args:
            module: Module source.
            check: Nom du check.
            severity: CRITICAL, HIGH, MEDIUM, LOW, ou INFO.
            status: PASS, FAIL, ou FIXED.
            description: Description détaillée.
            recommendation: Recommandation (optionnelle).
        """
        if severity not in SeverityLevel.ALL:
            raise ValueError(
                f"Sévérité invalide: '{severity}'. "
                f"Doit être l'un de: {', '.join(SeverityLevel.ALL)}"
            )
        if status not in ("PASS", "FAIL", "FIXED"):
            raise ValueError(
                f"Statut invalide: '{status}'. Doit être PASS, FAIL ou FIXED."
            )

        self.findings.append(
            Finding(
                module=module,
                check=check,
                severity=severity,
                status=status,
                description=description,
                recommendation=recommendation,
            )
        )

    def add_corrective_action(
        self, module: str, description: str, files: list[str] | None = None
    ) -> None:
        """Ajoute une action corrective appliquée.

        Args:
            module: Module concerné.
            description: Description du correctif.
            files: Liste des fichiers modifiés.
        """
        self.corrective_actions.append(
            CorrectiveAction(
                module=module,
                description=description,
                files=files or [],
            )
        )

    # ── Statistiques ──────────────────────────────────────────

    @property
    def total(self) -> int:
        return len(self.findings)

    @property
    def passed(self) -> int:
        return sum(1 for f in self.findings if f.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for f in self.findings if f.status == "FAIL")

    @property
    def fixed(self) -> int:
        return sum(1 for f in self.findings if f.status == "FIXED")

    def by_severity(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def critical_count(self) -> int:
        return len(self.by_severity(SeverityLevel.CRITICAL))

    @property
    def high_count(self) -> int:
        return len(self.by_severity(SeverityLevel.HIGH))

    @property
    def medium_count(self) -> int:
        return len(self.by_severity(SeverityLevel.MEDIUM))

    @property
    def low_count(self) -> int:
        return len(self.by_severity(SeverityLevel.LOW))

    @property
    def info_count(self) -> int:
        return len(self.by_severity(SeverityLevel.INFO))

    # ── Génération de rapport ─────────────────────────────────

    def generate_report(self, fmt: str = "text") -> str:
        """Génère le rapport d'audit formaté.

        Args:
            fmt: Format de sortie ("text" ou "json").

        Returns:
            Rapport formaté en texte ou JSON.
        """
        if fmt == "json":
            return self._generate_json()

        return self._generate_text()

    def _generate_text(self) -> str:
        """Génère un rapport texte formaté."""
        lines = [
            "╔" + "═" * 68 + "╗",
            "║  RAPPORT D'AUDIT DE SÉCURITÉ".ljust(57)
            + f" {self.timestamp[:10]} ║",
            "║  " + self.audit_title.ljust(56) + "║",
            "╚" + "═" * 68 + "╝",
            "",
            "📊 STATISTIQUES",
            "─" * 50,
            f"  Total checks       : {self.total}",
            f"  ✅ PASS            : {self.passed}",
            f"  ❌ FAIL            : {self.failed}",
            f"  🔧 FIXED           : {self.fixed}",
            "",
            f"  🔴 CRITICAL        : {self.critical_count}",
            f"  🟠 HIGH            : {self.high_count}",
            f"  🟡 MEDIUM          : {self.medium_count}",
            f"  🟢 LOW             : {self.low_count}",
            f"  ℹ️ INFO            : {self.info_count}",
            "",
        ]

        # Findings détaillés
        if self.findings:
            lines.append("📋 FINDINGS DÉTAILLÉS")
            lines.append("─" * 50)
            lines.append("")

            sorted_findings = sorted(
                self.findings,
                key=lambda f: (
                    SeverityLevel.sort_key(f.severity),
                    f.module,
                    f.check,
                ),
            )

            for f in sorted_findings:
                status_icon = {
                    "PASS": "✅",
                    "FAIL": "❌",
                    "FIXED": "🔧",
                }.get(f.status, "❓")

                severity_tag = {
                    "CRITICAL": "🔴 CRITICAL",
                    "HIGH": "🟠 HIGH",
                    "MEDIUM": "🟡 MEDIUM",
                    "LOW": "🟢 LOW",
                    "INFO": "ℹ️ INFO",
                }.get(f.severity, f.severity)

                lines.append(f"  [{severity_tag}] {status_icon}")
                lines.append(f"  Module : {f.module}")
                lines.append(f"  Check  : {f.check}")
                lines.append(f"  Detail : {f.description}")
                if f.recommendation:
                    lines.append(f"  →      : {f.recommendation}")
                lines.append("")

        # Actions correctives
        if self.corrective_actions:
            lines.append("🔧 ACTIONS CORRECTIVES APPLIQUÉES")
            lines.append("─" * 50)
            lines.append("")

            for ca in self.corrective_actions:
                lines.append(f"  Module : {ca.module}")
                lines.append(f"  Action : {ca.description}")
                if ca.files:
                    lines.append("  Fichiers modifiés :")
                    for f in ca.files:
                        lines.append(f"    - {f}")
                lines.append("")

        # Résumé
        lines.append("📈 RÉSUMÉ")
        lines.append("─" * 50)
        if self.failed == 0:
            lines.append("  ✅ Tous les checks de sécurité sont PASS ou FIXED.")
            lines.append("  L'audit est conforme.")
        else:
            lines.append(
                f"  ❌ {self.failed} check(s) en échec nécessitent "
                f"une attention immédiate."
            )
        lines.append("")
        lines.append("═" * 70)
        lines.append(f"  Rapport généré le {self.timestamp}")
        lines.append("═" * 70)

        return "\n".join(lines)

    def _generate_json(self) -> str:
        """Génère un rapport au format JSON."""
        data = {
            "title": self.audit_title,
            "timestamp": self.timestamp,
            "statistics": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "fixed": self.fixed,
                "by_severity": {
                    "critical": self.critical_count,
                    "high": self.high_count,
                    "medium": self.medium_count,
                    "low": self.low_count,
                    "info": self.info_count,
                },
            },
            "findings": [f.to_dict() for f in self.findings],
            "corrective_actions": [
                ca.to_dict() for ca in self.corrective_actions
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def export_json(self, path: str) -> None:
        """Exporte le rapport en JSON vers un fichier.

        Args:
            path: Chemin du fichier de sortie.
        """
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.generate_report(fmt="json"))

    def merge(self, other: AuditReport) -> None:
        """Fusionne les findings d'un autre rapport dans celui-ci.

        Args:
            other: Autre rapport AuditReport à fusionner.
        """
        self.findings.extend(other.findings)
        self.corrective_actions.extend(other.corrective_actions)


# ── Helper : generate_text_report ────────────────────────────────


def generate_report(
    findings: list[dict] | None = None,
    fix_summary: str | None = None,
) -> str:
    """Génère un rapport texte simple à partir de données brutes.

    Fonction utilitaire pour les cas où AuditReport n'est pas
    nécessaire.

    Args:
        findings: Liste de dicts avec clés module, check, severity,
                  status, description, recommendation.
        fix_summary: Résumé textuel des correctifs appliqués.

    Returns:
        Rapport texte formaté.
    """
    report = AuditReport()

    if findings:
        for f in findings:
            report.add_finding(
                module=f.get("module", "?"),
                check=f.get("check", "?"),
                severity=f.get("severity", "INFO"),
                status=f.get("status", "FAIL"),
                description=f.get("description", ""),
                recommendation=f.get("recommendation", ""),
            )

    if fix_summary:
        report.add_corrective_action(
            module="global",
            description=fix_summary,
        )

    return report.generate_report()
