import os
import asyncio
import requests
import logging
from threading import Thread

from flask import Flask
from flask import request, jsonify, make_response

from slack_sdk import WebClient 
import slack
from slackeventsapi import SlackEventAdapter
from slack_sdk.errors import SlackApiError

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

# Set up logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)

blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f" 🤓 Query:\n\n🧠 Answer:"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Choose whether to make the response visible:"
            },
            "accessory": {
                "type": "static_select",
                "action_id": "visibility_select",
                "options": [
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Make Response Visible"
                        },
                        "value": "visible"
                    },
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Hide Response"
                        },
                        "value": "hidden"
                    }
                ]
            }
        }
    ]

slack_token = os.environ.get('SLACK_BOT_TOKEN')
slack_client_id = os.environ.get('SLACK_CLIENT_ID')
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
SLACK_CLIENT_SECRET = os.environ["SLACK_CLIENT_SECRET"]

slack_events_adapter = SlackEventAdapter(SLACK_SIGNING_SECRET, "/slack/events", app)

#SLACK_VERIFICATION_TOKEN = os.environ["SLACK_VERIFICATION_TOKEN"]

client = WebClient(token=slack_token)

user_db = {}
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
  # save team id with corresponding auth access token to a databas!
  # dummy representation of a  database for now
  teamID = response["team"]["id"] 
  token_database[teamID] = response["access_token"]

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
        response_type='ephemeral',
        text="Getting your answer... to the question: " + request.form['text'],
    )


def respond_to_slack_message(res):
    payload = res

    try: 
        print("api call to open modal")
        api_response = client.views_open(
                        trigger_id=payload["trigger_id"],
                        view={
                            "type": "modal",
                            "callback_id": "modal-id",
                            "title": {
                                "type": "plain_text",
                                "text": "Awesome Modal"
                            },
                            "submit": {
                                "type": "plain_text",
                                "text": "Submit"
                            },
                            "blocks": [
                                {
                                    "type": "input",
                                    "block_id": "b-id",
                                    "label": {
                                        "type": "plain_text",
                                        "text": "Input label",
                                    },
                                    "element": {
                                        "action_id": "a-id",
                                        "type": "plain_text_input",
                                    }
                                }
                            ]
                        }
                    )
        print("api call over")
        print(api_response)
    except SlackApiError as e:
        code = e.response["error"]
        return make_response(f"failied to opne modal, code: {code}", 200)

    user_input = res['text']
    channel_id = res['channel_id'] 
    user_id = res['user_id']

    print("channel" + channel_id)
    print("user" + user_id)

    
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
    
    if user_id not in user_db:
       user_db[user_id] = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
       print("hello!!!! this is user database convo buffer")
       print(user_db.get(user_id))

    curr_memory = user_db.get(user_id)
    print("curr_memory")
    print(curr_memory.load_memory_variables({})

)

    conversation = LLMChain(
        llm=llm,
        prompt=prompt,
        verbose=True,
        memory=curr_memory
    )

    answer = conversation({"question": user_input})['text']
    curr_at = res['user_id']

    data = {
            'response_type': 'ephemeral',
            'text': f"<@{curr_at}>  \n 🤓 Query: " + res['text'] + "\n\n🧠 Answer: " + answer
            }
    
    requests.post(res['response_url'], json=data)

 
  #  client.chat_postMessage(
  #                          channel=channel_id,
   #                         text=(f"<@{curr_at}>  \n 🤓 Query: " + res['text'] + "\n\n🧠 Answer: " + answer) )
#
    return make_response("", 200)


@slack_events_adapter.on("app_home_opened")
def home_tab_opened(data):
    client.chat_postMessage(
    channel=data['event']['channel'],
    blocks=[
        # {
        #     "type": "section",
        #     "text": {
        #         "type": "mrkdwn",
        #         "text": "<https://example.com|Overlook Hotel> \n :star: \n Doors had too many axe holes, guest in room " +
        #             "237 was far too rowdy, whole place felt stuck in the 1920s."
        #     },
        #     "accessory": {
        #         "type": "image",
        #         "image_url": "https://images.pexels.com/photos/750319/pexels-photo-750319.jpeg",
        #         "alt_text": "Haunted hotel image"
        #     }
        # },
		{
			"type": "input",
			"element": {
				"type": "radio_buttons",
				"options": [
					{
						"text": {
							"type": "plain_text",
							"text": "yes",
						},
						"value": "yes"
					},
					{
						"text": {
							"type": "plain_text",
							"text": "no",
						},
						"value": "no"
					}
				],
				"action_id": "radio_buttons-action"
			},
			"label": {
				"type": "plain_text",
				"text": "Would you like the response to be visible to all in the channel?",
			}
		}
	]
)

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