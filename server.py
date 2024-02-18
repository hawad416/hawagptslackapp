import os
import asyncio
import requests
from threading import Thread

from flask import Flask
from flask import request, jsonify

from slack_sdk import WebClient 
import slack
from slackeventsapi import SlackEventAdapter


from langchain_community.chat_models import ChatOpenAI
from langchain.prompts.chat import (
    ChatPromptTemplate,
    MessagesPlaceholder,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory



app = Flask(__name__)

slack_token = os.environ.get('SLACK_BOT_TOKEN')
slack_client_id = os.environ.get('SLACK_CLIENT_ID')
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
SLACK_CLIENT_SECRET = os.environ["SLACK_CLIENT_SECRET"]

slack_events_adapter = SlackEventAdapter(SLACK_SIGNING_SECRET, "/slack/events", app)

#SLACK_VERIFICATION_TOKEN = os.environ["SLACK_VERIFICATION_TOKEN"]

client = WebClient(token=slack_token)

token_database = {}

llm = ChatOpenAI(temperature=0, model_name="gpt-4")
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)


def start_command_worker(loop):
    """Switch to new event loop and run forever"""
    asyncio.set_event_loop(loop)
    loop.run_forever()

command_loop = asyncio.new_event_loop()
command_worker = Thread(target=start_command_worker, args=(command_loop,))
command_worker.start()

@app.route("/")
def home():
  print(request)
  # Retrieve the auth code and state from the request params
  auth_code = request.args["code"]  
  print(auth_code)


  global client
  response = client.oauth_v2_access(
        client_id=slack_client_id,
        client_secret=SLACK_CLIENT_SECRET,
        code=auth_code
    )


  # Save the bot token and teamID to a database
  # In our example, we are saving it to dictionary to represent a DB  
  teamID = response["team"]["id"]
  token_database[teamID] = response["access_token"]

  client = slack.WebClient(token=slack_token)

  # testing this with the cseed workspace so hardocding cseed-announce channel for now
  #test convo creation later lmao
  #resp = client.conversations_create(name="cseed-announce")

  print(token_database)

  return "auth succesful!"
	
@app.route("/hawagpt", methods=['GET', 'POST'])
def get_slash_command():
    command_loop.call_soon_threadsafe(respond_to_slack_message,
                                      request.form)
    return jsonify(
        response_type='in_channel',
        text="Getting your answer... to the question: " + request.form['text'],
    )


def respond_to_slack_message(res):
    # look for current channel
    print(res)

    user_input = res['text']
    channel_id = res['channel_id'] 
    print("channel" + channel_id)
    
    prompt = ChatPromptTemplate(
        messages=[
            SystemMessagePromptTemplate.from_template(
                """You are a nice chatbot having a conversation with a human. You are a helpful assistant able to assist with a wide variety of tasks!
                If you don't know an answer, you say I dont know!
                """      
            ),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{question}")
        ]
    )

    conversation = LLMChain(
        llm=llm,
        prompt=prompt,
        verbose=True,
        memory=memory
    )

    answer = conversation({"question": user_input})['text']
    curr_at = res['user_id']

    data = {
            'response_type': 'in_channel',
            'text': f"<@{curr_at}>  \n 🤓 Query: " + res['text'] + "\n\n🧠 Answer: " + answer
            }
    
    requests.post(res['response_url'], json=data)

 
    client.chat_postMessage(
                            channel=channel_id,
                            text=(f"<@{curr_at}>  \n 🤓 Query: " + res['text'] + "\n\n🧠 Answer: " + answer) )

    return "ok"

#ok so bot should be mentioned in the channel to respond in that channel?
@staticmethod
@slack_events_adapter.on("app_mention")
def app_mentioned(data):
  print(data)
  user = data['event']['user']
  channel_id=data['event']['channel']

  responseText = (f'hi <@{user}>')
  response =client.chat_postMessage(
    channel=channel_id,
    user_id = user,
    user = user,
    text = responseText
  )


# Create an event listener for "reaction_added" events and print the emoji name
@slack_events_adapter.on("reaction_added")
def reaction_added(event_data):
  emoji = event_data["event"]["reaction"]
  print("reaction! " + emoji)


if __name__ == "__main__":
  app.run(port=8080)