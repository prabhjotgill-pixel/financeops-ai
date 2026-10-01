from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.core.financial import FinancialStatement, normalize_account_name
from backend.app.repositories.financials import TransactionData
from backend.app.schemas.accounts import AccountRead


@dataclass(frozen=True)
class ClassifiedTransaction:
    transaction: TransactionData
    account: AccountRead | None
    match_method: str | None
    exclusion_reason: str | None


def classify_transactions(
    rows: Sequence[TransactionData], accounts: Sequence[AccountRead]
) -> list[ClassifiedTransaction]:
    codes = {(item.company_id, item.account_code): item for item in accounts}
    names: dict[tuple[int, str], list[AccountRead]] = {}
    for item in accounts:
        names.setdefault(
            (item.company_id, normalize_account_name(item.account_name)), []
        ).append(item)
    result: list[ClassifiedTransaction] = []
    for row in rows:
        method: str | None = None
        reason: str | None = None
        account: AccountRead | None = None
        if row.account_code:
            account = codes.get((row.company_id, row.account_code.strip()))
            method = "code" if account else None
            if account is None:
                reason = "UNMATCHED_ACCOUNT_CODE"
        else:
            candidates = names.get(
                (row.company_id, normalize_account_name(row.account_name or "")), []
            )
            if len(candidates) == 1:
                account, method = candidates[0], "name"
            else:
                reason = (
                    "AMBIGUOUS_ACCOUNT_NAME" if candidates else "UNMATCHED_ACCOUNT_NAME"
                )
        if account is not None:
            if account.financial_category is None:
                reason = "UNCLASSIFIED_ACCOUNT"
            elif account.financial_statement == FinancialStatement.CASH_FLOW:
                reason = "CASH_FLOW_CLASSIFICATION_EXCLUDED"
        result.append(ClassifiedTransaction(row, account, method, reason))
    return result
