import os
from flask import Flask
from flask import request, jsonify
from slack_sdk import WebClient 
from slackeventsapi import SlackEventAdapter
from langchain import OpenAI, ConversationChain, LLMChain, PromptTemplate
from langchain.memory import ConversationBufferWindowMemory
from langchain_community.chat_models import ChatOpenAI
from threading import Thread
import asyncio
import requests


app = Flask(__name__)

slack_token = os.environ.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
#SLACK_VERIFICATION_TOKEN = os.environ["SLACK_VERIFICATION_TOKEN"]
client = WebClient(token=slack_token)

print(SLACK_SIGNING_SECRET)
print((slack_token))

#Langchain implementation
template = """Assistant is a large language model trained by OpenAI.

    Assistant is designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, Assistant is able to generate human-like text based on the input it receives, allowing it to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand.

    Assistant is constantly learning and improving, and its capabilities are constantly evolving. It is able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. Additionally, Assistant is able to generate its own text based on the input it receives, allowing it to engage in discussions and provide explanations and descriptions on a wide range of topics.

    Overall, Assistant is a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether you need help with a specific question or just want to have a conversation about a particular topic, Assistant is here to assist.

    {history}
    Human: {human_input}
    Assistant:"""

prompt = PromptTemplate(
    input_variables=["history", "human_input"], 
    template=template
)

open_ai = OpenAI(model_name="gpt-4-0125-preview", temperature=0)

chatgpt_chain = LLMChain(
    llm= open_ai, ##OpenAI(temperature=0), 
    prompt=prompt, 
    verbose=True, 
    memory=ConversationBufferWindowMemory(k=10),
)

def start_command_worker(loop):
    """Switch to new event loop and run forever"""
    asyncio.set_event_loop(loop)
    loop.run_forever()

command_loop = asyncio.new_event_loop()
command_worker = Thread(target=start_command_worker, args=(command_loop,))
command_worker.start()


## why do we need the route + other stuff
@app.route("/")
def hello():
   # response = client.chat_postMessage(
      #                  channel="slacktest",
       #                 text="hi hawa!!")
    return "ok"
	

@app.route("/hawagpt", methods=['GET', 'POST'])
def get_slash_command():
    command_loop.call_soon_threadsafe(hello_world,
                                      request.form)
    return jsonify(
        response_type='ephemeral',
        text="Getting your answer...",
    )


def hello_world(res):
    print("inthe hello world")
    user_input = res['text']
    print(user_input)
        
    # Implement your logic based on the user's input
        # For example, you can use it as input for your LangChain model
    output = chatgpt_chain.predict(human_input=user_input)


    data = {
            'response_type': 'ephemeral',
            'text': output
        }
    
    requests.post(res['response_url'], json=data)
    return output



# Bind the Events API route to your existing Flask app by passing the server
# instance as the last param, or with `server=app`.
slack_events_adapter = SlackEventAdapter(SLACK_SIGNING_SECRET, "/slack/events", app)

@staticmethod
@slack_events_adapter.on("app_mention")
def app_mentioned(data):
  print(data)
  user = data['event']['user']
  responseText = (f'hi <@{user}>')
  response =client.chat_postMessage(
    channel="slacktest",
    text = responseText
  )
  print(response)


# Create an event listener for "reaction_added" events and print the emoji name
@slack_events_adapter.on("reaction_added")
def reaction_added(event_data):
  emoji = event_data["event"]["reaction"]
  print(emoji)



#Message handler for Slack
@slack_events_adapter.on("app_mention")
def message_handler(message):
    awaitingResponse = True;
    print(message)
    output = chatgpt_chain.predict(human_input = message['event']['text'])          
    if(awaitingResponse):
        awaitingResponse = False;

        response = client.chat_postMessage(
                            channel="slacktest",
                            text=output) 

    return "ok"
    

@app.route('/testroute')
def ok():
  print("hawa")
  return "[]"


if __name__ == "__main__":
  app.run(port=8080)