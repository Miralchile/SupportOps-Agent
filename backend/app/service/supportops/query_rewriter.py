from typing import Any, Dict, List

from service.supportops.tools import call_json_llm, compact, normalize_text


QUERY_REWRITE_PROMPT = """
你是客服检索查询改写器。原查询没有召回足够证据，请结合意图与最近对话，生成一条更适合知识库和历史工单检索的查询。

要求：
1. 保留订单、账号、报错代码等关键实体；
2. 补充意图同义表达，但不要虚构事实；
3. 只输出 JSON：{{"query": "...", "reason": "..."}}。

原查询：{question}
意图分类：{classification}
最近对话：{history}
""".strip()


def rewrite_query(
    question: str,
    classification: Dict[str, Any],
    messages: List[Dict[str, Any]],
) -> Dict[str, str]:
    fallback = {
        "query": question,
        "reason": "模型不可用或未生成有效改写，继续使用原查询。",
    }
    prompt = QUERY_REWRITE_PROMPT.format(
        question=question,
        classification=compact(classification),
        history=compact(messages[-6:]),
    )
    result = call_json_llm(prompt, fallback)
    query = normalize_text(result.get("query")) or question
    return {
        "query": query,
        "reason": normalize_text(result.get("reason")) or fallback["reason"],
    }
