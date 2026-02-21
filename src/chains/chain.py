import os
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_openai import ChatOpenAI
from langchain.prompts.prompt import PromptTemplate

# 1. Connect to your Omics KG
graph = Neo4jGraph(
    url=os.getenv("NEO4J_URI"),
    username=os.getenv("NEO4J_USERNAME"),
    password=os.getenv("NEO4J_PASSWORD")
)

# 2. Define the Specialized "Bio-Cypher" Prompt
# This tells the LLM exactly how to handle your specific schema.
OMICS_CYPHER_TEMPLATE = """Task: Generate a Cypher statement to query a marine microbial knowledge graph.
Instructions:
Use only the provided relationship types and properties in the schema.
Statistical Guardrail: For any transcriptomic result (UPREGULATED_IN/DOWNREGULATED_IN), always filter by 'adj_pValue < 0.05'.
Directionality: Remember that Prochlorococcus (phototroph) often provides carbon to Alteromonas (heterotroph).

Schema:
{schema}

Example Questions:
- "Which genes in Prochlorococcus MED4 are upregulated during nitrogen starvation?"
- "Find the Alteromonas proteins involved in ROS detoxification with a log2FoldChange > 2."

Question: {question}
Cypher Query:"""

CYPHER_PROMPT = PromptTemplate(
    input_variables=["schema", "question"], 
    template=OMICS_CYPHER_TEMPLATE
)

# 3. Initialize the Chain
llm = ChatOpenAI(model="gpt-4o", temperature=0)

chain = GraphCypherQAChain.from_llm(
    llm=llm,
    graph=graph,
    verbose=True,
    cypher_prompt=CYPHER_PROMPT,
    allow_dangerous_requests=True # Required in latest LangChain versions
)

# 4. Example Usage
# response = chain.invoke({"query": "Identify Alteromonas genes upregulated in co-culture with Prochlorococcus."})