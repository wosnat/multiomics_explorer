# multiomics_explorer
An agentic LLM application to explore and analyze multi-omics data. Targeting the interaction between the marine bacteria Prochlorococcus and Alteromonas.


# Omics-KG Agent: Deciphering Microbial Interdependencies

An agentic application built with **LangChain** and **Neo4j** to analyze multi-omics interactions between *Prochlorococcus* and *Alteromonas*. This system uses a Knowledge Graph (KG) to move beyond descriptive observations toward mechanistic discovery (ROS detoxification, Nitrogen recycling, and cross-feeding).

## 🧬 System Architecture
- **Database:** Neo4j (Graph Database)
- **Orchestration:** LangChain / LangGraph
- **LLM:** GPT-4o or Claude 3.7 Sonnet (via LangChain)
- **Data Sources:** NCBI, Cyanorak (CLOGs), UniProt, and 19 Transcriptome studies.

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- A running Neo4j instance (AuraDB or Local Docker)
- OpenAI or Anthropic API Key

### 2. Installation
```bash
git clone [https://github.com/your-repo/omics-graph-agent.git](https://github.com/your-repo/omics-graph-agent.git)
cd omics-graph-agent
pip install -r requirements.txt