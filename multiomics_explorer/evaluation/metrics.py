"""Evaluation metrics for the agent pipeline.

Combines RAGAS metrics (faithfulness, answer_relevance) with
custom biology validators for the Prochlorococcus domain.

TODO: Implement RAGAS integration and custom validators:
- check_gene_existence: verify returned gene IDs exist in KG
- check_organism_accuracy: verify strain names and genera
- check_expression_direction: validate up/down consistency
- llm_as_judge: biological correctness scoring (1-5)
"""
