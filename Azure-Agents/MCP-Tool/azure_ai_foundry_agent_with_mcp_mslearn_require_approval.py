# Azure AI Foundry Agent with Model Context Protocol (MCP) Demo
# Source: https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/model-context-protocol-samples?pivots=python

# Import necessary libraries
import os, time
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import McpTool, RequiredMcpToolCall, SubmitToolApprovalAction, ToolApproval, MessageRole, ThreadMessage
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional


# Load environment variables from .env file
load_dotenv()
# Get the MCP server configuration from environment variables
mcp_server_url = os.environ.get("MCP_SERVER_URL", "https://learn.microsoft.com/api/mcp")
mcp_server_label = os.environ.get("MCP_SERVER_LABEL", "mslearn")

agent_name = "MSLearn MCP Agent"
first_message = "AI Foundray这个产品，最近一周有哪些文档的更新？"

project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

# Set up the MCP tool
mcp_tool = McpTool(
    server_label=mcp_server_label,
    server_url=mcp_server_url,
    allowed_tools=[],  # Optional: specify allowed tools
)
# mcp_tool.set_approval_mode("never")  # Set approval mode to never for this demo

# You can also add or remove allowed tools dynamically
# search_api_code = "search_azure_rest_api_code"
# mcp_tool.allow_tool(search_api_code)
# print(f"Allowed tools: {mcp_tool.allowed_tools}")

# Handle tool approvals
# mcp_tool.update_headers("SuperSecret", "123456")


def fetch_and_print_new_agent_response(
    thread_id: str,
    agents_client: AgentsClient,
    last_message_id: Optional[str] = None,
) -> Optional[str]:
    lastest_agent_message = agents_client.messages.get_last_message_by_role(
        thread_id=thread_id,
        role=MessageRole.AGENT,
    )
    if not lastest_agent_message or lastest_agent_message.id == last_message_id:
        print(f"😶 No new content. last_message_id: {last_message_id}")
        return last_message_id  # No new content

    print(f"\n===================== 🤖 Agent response with lastest_agent_message id: {lastest_agent_message.id} ===========================")
    print("\n".join(t.text.value for t in lastest_agent_message.text_messages))

    for ann in lastest_agent_message.url_citation_annotations:
        print(f"****** 🛜 URL Citation ******:\n   [{ann.url_citation.title}]({ann.url_citation.url})")

    return lastest_agent_message.id

def process_agent_run(agents_client: AgentsClient, thread_id: str, agent_id: str, user_message: str, tool_resources) -> None:
    """Process a single agent run with the given user message"""
    # Create message to thread
    message = agents_client.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message,
    )
    print(f"Created message, ID: {message.id}")
    print(f"👤 User message: {user_message}")

    print(f"Start processing the message... this may take a few minutes to finish. Be patient!")
    # Poll the run as long as run status is queued or in progress
    run = agents_client.runs.create(thread_id=thread_id, agent_id=agent_id,
                                    tool_resources=tool_resources)
    last_message_id = None
    while run.status in ("queued", "in_progress", "requires_action"):
        time.sleep(2)
        run = agents_client.runs.get(thread_id=thread_id, run_id=run.id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"\n\n🔄🔄🔄 Run status: {run.status} at {timestamp}")
        if run.status == "requires_action":
            print("Run requires action, checking for tool calls...")
            
            # 检查是否需要工具审批
            if isinstance(run.required_action, SubmitToolApprovalAction):
                print("Tool approval required!")
                tool_calls = run.required_action.submit_tool_approval.tool_calls
                
                # 创建审批列表
                tool_approvals = []
                for tool_call in tool_calls:
                    if isinstance(tool_call, RequiredMcpToolCall):
                        print(f"  Tool Call ID: {tool_call.id}")
                        print(f"  Tool Name: {tool_call.name}")
                        print(f"  Server Label: {tool_call.server_label}")
                        print(f"  Arguments: {tool_call.arguments}")
                        
                        # 询问用户是否批准此工具调用
                        user_approval = input(f"Do you approve the tool call '{tool_call.name}'? (y/n): ").strip().lower()
                        approve = user_approval in ['y', 'yes', '1', 'true']
                        
                        # 创建 ToolApproval 对象
                        approval = ToolApproval(
                            tool_call_id=tool_call.id,
                            approve=approve
                        )
                        tool_approvals.append(approval)
                        
                        print(f"  Approval: {'Approved' if approve else 'Denied'}")
                
                # 提交工具审批
                if tool_approvals:
                    print("Submitting tool approvals...")
                    agents_client.runs.submit_tool_outputs(
                        thread_id=thread_id,
                        run_id=run.id,
                        tool_approvals=tool_approvals
                    )
                    print("Tool approvals submitted!")
                   
            else:
                print(f"Required action type: {run.required_action.type if run.required_action else 'None'}")
           

        last_message_id = fetch_and_print_new_agent_response(
            thread_id=thread_id,
            agents_client=agents_client,
            last_message_id=last_message_id,
        )

    print(f"\n\n🎉🎉🎉 Run finished with status: {run.status}, ID: {run.id}")

    if run.status == "failed":
        print(f"Run failed: {run.last_error}")
        return

    # Fetch the final message from the agent in the thread and create a research summary
    final_message = agents_client.messages.get_last_message_by_role(
        thread_id=thread_id, role=MessageRole.AGENT
    )
    if final_message:
        print(f"Final agent Message ID: {final_message.id}")
        # print(f"\n\n🤖 Final agent message: \n{final_message.content}")
        print(f"\n\n🤖 Final agent message: \n")
        print("\n".join(t.text.value for t in final_message.text_messages))
    
    
    # Retrieve the steps taken during the run for analysis
    run_steps = agents_client.run_steps.list(thread_id=thread.id, run_id=run.id)

    # Loop through each step to display information
    for step in run_steps:
        print(f"Step {step['id']} status: {step['status']}")

        tool_calls = step.get("step_details", {}).get("tool_calls", [])
        for call in tool_calls:
            print(f"  Tool Call ID: {call.get('id')}")
            print(f"  Type: {call.get('type')}")
            print(f"  Name: {call.get('name')}")
            print(f"  Server Label: {call.get('server_label')}")
            print(f"  Arguments: {call.get('arguments')}")
            print(f"  Output: {call.get('output')}")
            # function_details = call.get("function", {})
            # if function_details:
            #     print(f"  Function name: {function_details.get('name')}")
            #     print(f"  Function output: {function_details.get('output')}")
        print()



# Create an agent
# NOTE: To reuse an existing agent, fetch it with get_agent(agent_id)
with project_client:
    agents_client = project_client.agents

    # Create a new agent.
    # NOTE: To reuse an existing agent, fetch it with get_agent(agent_id)
    agent = agents_client.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        name=agent_name,
        instructions="You are a helpful agent that can use MCP tools to assist users. Use the available MCP tools to answer questions and perform tasks.",
        tools=mcp_tool.definitions,
    )
    print(f"Created agent, ID: {agent.id}")

    # Create a thread for communication
    thread = agents_client.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Multi-turn conversation loop
    # first_message = "AI Foundray这个产品，最近一周有哪些文档的更新？"
    current_message = first_message
    
    while True:
        # Process the current message
        process_agent_run(agents_client, thread.id, agent.id, current_message, tool_resources=mcp_tool.resources)
        
        # Ask user if they want to continue
        print("\n" + "="*60)
        user_input = input("Do you want to continue the conversation? Enter 'n' to quit, or type your next question: ")
        print(f"********* 💬 User input: {user_input} *********")
        
        # Check if user wants to quit
        if user_input.strip().lower() == 'n':
            print("Ending conversation...")
            break
        
        # Use user input as the next message
        current_message = user_input.strip()
        if not current_message:
            print("Empty message, ending conversation...")
            break

    # # Create and automatically process the run, handling tool calls internally
    # run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    # print(f"Run finished with status: {run.status}")

    # if run.status == "failed":
    #     print(f"Run failed: {run.last_error}")


    # Perform cleanup
    # Delete the agent resource to clean up
    # project_client.agents.delete_agent(agent.id)
    # print("Deleted agent")

    # Fetch and log all messages exchanged during the conversation thread
    messages = agents_client.messages.list(thread_id=thread.id)
    for msg in messages:
        print(f"Message ID: {msg.id}, \nRole: {msg.role}, \nContent: {msg.content}\n\n")
