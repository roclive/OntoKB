from ontokb.api import _relations_table


def test_relations_table_matches_expected_shape():
    text = _relations_table(
        [
            {
                "triple_id": 72,
                "relation": "Codex -- uses -> harness agent",
            }
        ]
    )

    assert text == "相关关系如下：\ntriple_id\t关系\n72\tCodex -- uses -> harness agent\n"
