"""Dynamic vocabulary manager for learning and resolving alternative invoice field names.

Maintains canonical field mappings and uses a lightweight LLM (gpt-4o-mini)
to discover and register new aliases when mandatory fields are missing.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default canonical invoice fields
CANONICAL_FIELDS = {
    "invoice_id": [
        # English
        "invoice_number", "invoice_no", "inv_number", "inv_no", "inv #", "inv no",
        "id", "bill_no", "bill_number", "folio", "reference_number", "ref_no", "doc_no",
        # French
        "numero_facture", "numero", "num_facture", "no_facture", "n_facture",
        "numero_de_facture", "reference", "ref_facture",
        # Spanish
        "numero_factura", "num_factura", "no_factura", "folio_factura",
        # German
        "rechnungsnummer", "rechnung_nr", "beleg_nr",
        # Portuguese
        "numero_fatura", "num_fatura",
    ],
    "date": [
        # English
        "invoice_date", "issue_date", "dt", "invoicedate", "bill_date", "date_issued",
        # French
        "date_facture", "date_emission", "date_etablissement",
        # Spanish
        "fecha", "fecha_factura", "fecha_emision",
        # German
        "datum", "rechnungsdatum", "ausstellungsdatum",
        # Portuguese
        "data", "data_fatura",
    ],
    "due_date": [
        # English
        "due_dt", "payment_due", "due", "payment_due_date", "pay_by", "settlement_date",
        # French
        "date_echeance", "echeance", "date_limite", "date_paiement", "date_limite_paiement",
        # Spanish
        "fecha_vencimiento", "vencimiento", "fecha_limite",
        # German
        "faelligkeitsdatum", "zahlungsziel", "faelligkeit",
        # Portuguese
        "data_vencimento", "vencimento",
    ],
    "vendor": [
        # English
        "vendor_name", "vndr", "supplier", "seller", "biller", "provider", "company",
        "merchant", "remit_to", "payee",
        # French
        "fournisseur", "vendeur", "prestataire", "emetteur", "societe",
        # Spanish
        "proveedor", "vendedor", "emisor", "empresa",
        # German
        "lieferant", "haendler", "anbieter", "verkäufer", "firma",
        # Portuguese
        "fornecedor", "vendedor", "emissor",
    ],
    "line_items": [
        # English
        "items", "lines", "articles", "products", "item_list", "entries", "order_lines",
        # French
        "lignes", "lignes_de_facture", "postes", "prestations",
        # Spanish
        "articulos", "lineas", "productos", "detalle",
        # German
        "positionen", "artikel", "leistungen",
        # Portuguese
        "itens", "linhas",
    ],
    "subtotal": [
        # English
        "net_amount", "pre_tax_amount", "base_amount", "sub_total",
        # French
        "sous_total", "montant_ht", "total_ht", "montant_hors_taxe", "hors_taxe",
        # Spanish
        "subtotal", "importe_neto", "base_imponible",
        # German
        "nettobetrag", "zwischensumme",
        # Portuguese
        "subtotal", "valor_liquido",
    ],
    "tax_rate": [
        # English
        "vat_rate", "tax_pct", "tax_percentage", "gst_rate",
        # French
        "taux_taxe", "taux_tva", "taux_de_taxe", "tva_pct", "taux",
        # Spanish
        "tasa_impuesto", "tasa_iva", "porcentaje_iva",
        # German
        "steuersatz", "mehrwertsteuersatz", "mwst_satz",
        # Portuguese
        "taxa_imposto", "taxa_iva",
    ],
    "tax_amount": [
        # English
        "tax", "vat_amount", "vat", "gst_amount", "gst", "tax_total",
        # French
        "montant_taxe", "montant_tva", "tva", "taxe", "taxe_totale",
        # Spanish
        "importe_iva", "iva", "impuesto", "total_impuesto",
        # German
        "steuerbetrag", "mehrwertsteuer", "mwst",
        # Portuguese
        "valor_imposto", "iva",
    ],
    "total": [
        # English
        "total_amount", "grand_total", "final_amount", "amt", "amount_due",
        "net_payable", "balance_due",
        # French
        "total_ttc", "montant_total", "total_general", "total_a_payer",
        # Spanish
        "total", "total_a_pagar", "importe_total",
        # German
        "gesamtbetrag", "endbetrag", "rechnungsbetrag",
        # Portuguese
        "total", "valor_total",
    ],
    "currency": [
        # English
        "curr", "currency_code", "iso_currency", "monetary_unit",
        # French
        "devise", "monnaie", "code_devise",
        # Spanish
        "moneda", "divisa",
        # German
        "waehrung", "währung",
        # Portuguese
        "moeda",
    ],
    "payment_terms": [
        # English
        "terms", "pymnt_terms", "payment_term", "payment_conditions", "credit_terms",
        # French
        "conditions_paiement", "modalites_paiement", "delai_paiement", "termes_paiement",
        # Spanish
        "condiciones_pago", "terminos_pago", "plazo_pago",
        # German
        "zahlungsbedingungen", "zahlungsziele",
        # Portuguese
        "condicoes_pagamento", "termos_pagamento",
    ],
    "shipping": [
        # English
        "shipping_cost", "freight", "delivery", "postage", "shipping_fee",
        # French
        "frais_livraison", "frais_expedition", "livraison", "transport",
        # Spanish
        "envio", "flete", "gastos_envio",
        # German
        "versandkosten", "frachtkosten",
    ],
    "notes": [
        # English
        "note", "comment", "comments", "remarks", "memo", "instructions",
        # French
        "notes", "remarques", "observations", "commentaires", "instructions",
        # Spanish
        "notas", "observaciones", "comentarios",
        # German
        "anmerkungen", "hinweise", "bemerkungen",
    ],
    "revision": [
        "rev", "revision_id", "version", "amendment",
    ],
}

LINE_ITEM_FIELDS = {
    "item": [
        # English
        "name", "description", "product", "desc", "title", "service", "article",
        # French
        "libelle", "designation",
        # Spanish
        "descripcion", "articulo", "producto",
        # German
        "bezeichnung", "beschreibung", "artikel",
    ],
    "quantity": [
        # English
        "qty", "count", "units", "amount_ordered", "volume", "qnty",
        # French
        "quantite", "qte", "nombre",
        # Spanish
        "cantidad", "unidades",
        # German
        "menge", "anzahl", "stueck",
        # Portuguese
        "quantidade",
    ],
    "unit_price": [
        # English
        "price", "rate", "unit_cost", "cost_per_unit", "each", "unit price",
        # French
        "prix_unitaire", "prix", "tarif", "cout_unitaire",
        # Spanish
        "precio_unitario", "precio", "valor_unitario",
        # German
        "einzelpreis", "stueckpreis", "preis",
        # Portuguese
        "preco_unitario", "preco",
    ],
    "amount": [
        # English
        "line_total", "total", "line_amount", "subtotal", "cost", "total_price",
        # French
        "montant", "montant_ligne", "total_ligne",
        # Spanish
        "importe", "total_linea",
        # German
        "betrag", "gesamtpreis",
    ],
    "note": ["notes", "discount", "comment", "detail"],
}


class VocabularyManager:
    """Manages alias-to-canonical field mappings with dynamic learning."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self._aliases: dict[str, str] = {}
        self._line_item_aliases: dict[str, str] = {}
        self._init_defaults()
        if self.db_path:
            self._load_from_db()

    def _init_defaults(self) -> None:
        """Seed default canonical mappings."""
        for canonical, aliases in CANONICAL_FIELDS.items():
            self._aliases[canonical.lower()] = canonical
            for alias in aliases:
                self._aliases[alias.lower().replace(" ", "_")] = canonical
                self._aliases[alias.lower()] = canonical

        for canonical, aliases in LINE_ITEM_FIELDS.items():
            self._line_item_aliases[canonical.lower()] = canonical
            for alias in aliases:
                self._line_item_aliases[alias.lower().replace(" ", "_")] = canonical
                self._line_item_aliases[alias.lower()] = canonical

    def _load_from_db(self) -> None:
        """Load persistent learned vocabulary from database."""
        if not self.db_path or not self.db_path.exists():
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT raw_alias, canonical_field, is_line_item FROM field_vocabulary"
                )
                for raw_alias, canonical, is_li in cursor.fetchall():
                    clean_alias = raw_alias.lower().strip()
                    if is_li:
                        self._line_item_aliases[clean_alias] = canonical
                    else:
                        self._aliases[clean_alias] = canonical
        except sqlite3.OperationalError:
            pass  # Table may not exist yet

    def get_aliases_for(self, canonical_field: str, is_line_item: bool = False) -> list[str]:
        """Get all aliases currently registered for a canonical field (longest first)."""
        lookup = self._line_item_aliases if is_line_item else self._aliases
        aliases = {alias for alias, canon in lookup.items() if canon == canonical_field}
        aliases.add(canonical_field)
        return sorted(aliases, key=len, reverse=True)

    def resolve(self, raw_key: str, is_line_item: bool = False) -> str | None:
        """Resolve a raw key name to its canonical field name."""
        if not raw_key:
            return None
        clean = raw_key.lower().strip()
        clean_norm = clean.replace(" ", "_").replace("-", "_")

        lookup = self._line_item_aliases if is_line_item else self._aliases
        return lookup.get(clean) or lookup.get(clean_norm)

    def register_alias(
        self,
        raw_alias: str,
        canonical_field: str,
        is_line_item: bool = False,
        source: str = "llm",
    ) -> None:
        """Register a newly discovered alias in memory and SQLite."""
        clean = raw_alias.lower().strip()
        clean_norm = clean.replace(" ", "_").replace("-", "_")

        if is_line_item:
            self._line_item_aliases[clean] = canonical_field
            self._line_item_aliases[clean_norm] = canonical_field
        else:
            self._aliases[clean] = canonical_field
            self._aliases[clean_norm] = canonical_field

        logger.info(
            "Learned new field alias: '%s' -> '%s' (line_item=%s, source=%s)",
            raw_alias,
            canonical_field,
            is_line_item,
            source,
        )

        if self.db_path:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS field_vocabulary (
                            raw_alias TEXT PRIMARY KEY,
                            canonical_field TEXT NOT NULL,
                            is_line_item INTEGER DEFAULT 0,
                            learned_from TEXT DEFAULT 'llm',
                            created_at TEXT DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO field_vocabulary
                        (raw_alias, canonical_field, is_line_item, learned_from)
                        VALUES (?, ?, ?, ?)
                        """,
                        (clean, canonical_field, int(is_line_item), source),
                    )
                    conn.commit()
            except Exception as e:
                logger.warning("Could not persist alias to database: %s", e)

    def learn_mappings_with_llm(
        self,
        unmatched_keys: list[str],
        missing_fields: list[str],
        sample_values: dict[str, Any] | None = None,
        llm_client: Any = None,
        is_line_item: bool = False,
    ) -> dict[str, str]:
        """Ask the lightest LLM to map unmatched keys to missing canonical fields, and learn them."""
        if not unmatched_keys or not missing_fields or llm_client is None:
            return {}

        learned = llm_client.map_alternative_fields(
            unmatched_keys=unmatched_keys,
            missing_fields=missing_fields,
            sample_values=sample_values or {},
            is_line_item=is_line_item,
        )

        for raw_k, canonical in learned.items():
            if canonical in (LINE_ITEM_FIELDS if is_line_item else CANONICAL_FIELDS):
                self.register_alias(
                    raw_alias=raw_k,
                    canonical_field=canonical,
                    is_line_item=is_line_item,
                    source="light_llm",
                )

        return learned


# Global singleton instance
_default_manager: VocabularyManager | None = None


def get_vocabulary_manager(db_path: str | Path | None = None) -> VocabularyManager:
    """Retrieve or initialize the vocabulary manager."""
    global _default_manager
    if _default_manager is None or db_path is not None:
        _default_manager = VocabularyManager(db_path)
    return _default_manager
