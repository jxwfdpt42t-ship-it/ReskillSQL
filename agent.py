import argparse
import os
import sys

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from dotenv import load_dotenv
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from rich.console import Console
from rich.panel import Panel

# Load environment variables
load_dotenv()

console = Console()


def create_model():
    """Create the chat model from an OpenAI-compatible env config."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    api_key = os.getenv("OPENAI_API_KEY") or gemini_key or os.getenv("OPENAI_API_KEY_2")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_name = os.getenv("MODEL_NAME")

    using_gemini = bool(gemini_key) and api_key == gemini_key
    if using_gemini:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        if not model_name or not model_name.startswith("gemini-"):
            model_name = "gemini-2.5-flash"
    elif not base_url:
        base_url = os.getenv("OPENAI_BASE_URL_2")
    if not model_name:
        model_name = "gpt-4.1"

    if not api_key or not base_url:
        raise RuntimeError(
            "Missing model credentials. Set OPENAI_API_KEY/OPENAI_BASE_URL, "
            "OPENAI_API_KEY_2/OPENAI_BASE_URL_2, or GEMINI_API_KEY."
        )

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )


def create_sql_deep_agent():
    """Create and return a text-to-SQL Deep Agent"""

    # Get base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Connect to Chinook database
    db_path = os.path.join(base_dir, "chinook.db")
    db = SQLDatabase.from_uri(f"sqlite:///{db_path}", sample_rows_in_table_info=3)

    # Initialize the model through an OpenAI-compatible endpoint.
    model = create_model()

    # Create SQL toolkit and get tools
    toolkit = SQLDatabaseToolkit(db=db, llm=model)
    sql_tools = toolkit.get_tools()

    # Create the Deep Agent with all parameters
    agent = create_deep_agent(
        model=model,  # Claude Sonnet 4.5 with temperature=0
        memory=["./AGENTS.md"],  # Agent identity and general instructions
        skills=[
            "./skills/"
        ],  # Specialized workflows (query-writing, schema-exploration)
        tools=sql_tools,  # SQL database tools
        subagents=[],  # No subagents needed
        backend=FilesystemBackend(root_dir=base_dir),  # Persistent file storage
    )

    return agent


def main():
    """Main entry point for the SQL Deep Agent CLI"""
    parser = argparse.ArgumentParser(
        description="Text-to-SQL Deep Agent powered by LangChain Deep Agents and GPT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent.py "What are the top 5 best-selling artists?"
  python agent.py "Which employee generated the most revenue by country?"
  python agent.py "How many customers are from Canada?"
        """,
    )
    parser.add_argument(
        "question",
        type=str,
        help="Natural language question to answer using the Chinook database",
    )

    args = parser.parse_args()

    # Display the question
    console.print(
        Panel(f"[bold cyan]Question:[/bold cyan] {args.question}", border_style="cyan")
    )
    console.print()

    # Create the agent
    console.print("[dim]Creating SQL Deep Agent...[/dim]")
    agent = create_sql_deep_agent()

    # Invoke the agent
    console.print("[dim]Processing query...[/dim]\n")

    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": args.question}]}
        )

        # Extract and display the final answer
        final_message = result["messages"][-1]
        answer = (
            final_message.content
            if hasattr(final_message, "content")
            else str(final_message)
        )

        console.print(
            Panel(f"[bold green]Answer:[/bold green]\n\n{answer}", border_style="green")
        )

    except Exception as e:
        console.print(
            Panel(f"[bold red]Error:[/bold red]\n\n{str(e)}", border_style="red")
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
