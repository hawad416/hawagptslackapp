import os
import asyncio
import requests
import logging
import requests
import validators
from threading import Thread

from flask import Flask
from flask import request, jsonify, make_response
from bs4 import BeautifulSoup as bs4

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

slack_token = os.environ.get('SLACK_BOT_TOKEN')
slack_client_id = os.environ.get('SLACK_CLIENT_ID')
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
SLACK_CLIENT_SECRET = os.environ["SLACK_CLIENT_SECRET"]

slack_events_adapter = SlackEventAdapter(SLACK_SIGNING_SECRET, "/slack/events", app)

client = WebClient(token=slack_token)

user_db = {}
app_opened_tracker = {}
token_database = {}

cached_link_sumarries = {}

llm = ChatOpenAI(temperature=0, model_name="gpt-4-0125-preview")
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

  auth_code = request.args["code"] 
  logging.info("Recieved auth code for oauth from slack: ", auth_code) 
  print(auth_code)

  global client
  response = client.oauth_v2_access(
        client_id=slack_client_id,
        client_secret=SLACK_CLIENT_SECRET,
        code=auth_code
    )
  logging.info("Exchanged Auth Code for Oauth V2 Access", response) 

  # save team id with corresponding auth access token to a database!
  # dummy representation of a  database for now
  teamID = response["team"]["id"] 
  token_database[teamID] = response["access_token"]

  logging.info("Team ID & Coressponding Bot Token Saved to Temporary DB", token_database) 

  return "Authorization Succesful. Check out HawaGPT in your Slack Workspace!"
	
@app.route("/hawagpt", methods=['GET', 'POST'])
def get_slash_command():
    logging.info("HawaGPT Slack Command Invoked") 

    command_loop.call_soon_threadsafe(respond_to_slack_message,
                                      request.form)    
    return jsonify(
        response_type='ephemeral',
        text="Getting your answer... to the question: " + request.form['text'],
    )

@app.route("/gibbs", methods=['GET', 'POST'])
def validate_url():
    res = request.form
    page = ""
    url_link =res['text']
    URL = ""

    if(validators.url(url_link)):
        URL = url_link

    if(URL == ""):
        return jsonify(response_type="ephemeral", text="Invalid URL Format. Please try again with a valid URL")
    

    if(url_link in cached_link_sumarries):
         answer = cached_link_sumarries[url_link]

         return jsonify(
            response_type='in_channel',
            text=f"🔗 {url_link}  \n \n {answer} \n\nSummary brought to you by Gibbs™ (Copyright © 2024 Madrona Venture Labs and IGBB Productions. All Rights Reserved.)",
         )
                
    page = requests.get(URL)

    command_loop.call_soon_threadsafe(scrape_and_summarize, url_link,
                                      page, res['response_url'])    
    return jsonify(
        response_type='ephemeral',
        text="Summarizing Link... " + request.form['text'],
    )

def scrape_and_summarize(link, page, response_url):
   page_contents = page.content
   soup = bs4(page_contents, "html.parser")

   body = soup.find("body").text.strip()
   # 'p, pre, article, blockquote, h1, h2, h3, h4, h5, h6' and maybe 'li'

   max_length = 8192
   #truncated_body = body[:max_length]

    # return raw text or summary (flag) 

   prompt = ChatPromptTemplate(
        messages=[
            SystemMessagePromptTemplate.from_template(
                """Extract the key 3-4 main ideas from this document, including what would be useful to know from it. Keep your response to a short paragraph with 3-4 sentences.
                If you don't know an answer, you say I dont know!
                """     
            ),
            HumanMessagePromptTemplate.from_template("{question}")
        ]
    )
   
   memory = ConversationBufferMemory()
   
   conversation = LLMChain(
        llm=llm,
        prompt=prompt,
        verbose=True,
        memory=memory
    )

   answer = conversation({"question": body})['text']
   data = {
            'response_type': 'in_channel',
            'text': f"🔗 {link}  \n \n {answer} \n\nSummary brought to you by Gibbs™ (Copyright © 2024 Madrona Venture Labs and IGBB Productions. All Rights Reserved.)"  
        }
    
   requests.post(response_url, json=data)
   cached_link_sumarries[link] = answer



def respond_to_slack_message(res):

    logging.info("Slack Slash Command Event", res)
    user_input = res['text']
    channel_id = res['channel_id'] 
    user_id = res['user_id']

    logging.info(f"Question asked by User: + {user_id} +  in channel  {channel_id}") 


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

    logging.info("Prompting Started")
    
    if user_id not in user_db:
       user_db[user_id] = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
       logging.info("New conversation memory buffer created for {user_id}")

    curr_memory = user_db.get(user_id)
    logging.info(f"Conversation Memory for user: {user_id}", curr_memory.load_memory_variables({}))

    logging.info("Creating LLMChain...")
    conversation = LLMChain(
        llm=llm,
        prompt=prompt,
        verbose=True,
        memory=curr_memory
    )

    answer = conversation({"question": user_input})['text']
    logging.info("Answer Received")
    curr_at = res['user_id']

    data = {
            'response_type': 'ephemeral',
            'text': f"<@{curr_at}> \n" +  answer
            }
    
    requests.post(res['response_url'], json=data)
    logging.info("Response Posted to Slack!")

 
  #  client.chat_postMessage(
  #                          channel=channel_id,
   #                         text=(f"<@{curr_at}>  \n 🤓 Query: " + res['text'] + "\n\n🧠 Answer: " + answer) )
#
    return make_response("", 200)


@slack_events_adapter.on("app_home_opened")
def home_tab_opened(data):
    logging.info("app_home_opened slack event! ", data)
    user_id = data["authorizations"][0]["user_id"]

    if(user_id not in app_opened_tracker):
        client.chat_postMessage(
            text="Welcome to HawaGPT! You can use the slash command /hawagpt to get your questions answered & /gibbs to get link summaries!",
            channel=data['event']['channel'],
        )
        app_opened_tracker[user_id] = True


# @slack_events_adapter.on("message")
# def message(event_data):
#    print("message detected!")
#    print(event_data)

#    page = ""
#    url_link = ""
#    URL = ""

#    if(validators.url(url_link)):
#         URL = url_link
#         print("url valid")
#    else:
#       return 
   
#    page = requests.get(url_link)

#    scrape_and_summarize_2(url_link, page.content, event_data)

#    print("called method?")

   
# def scrape_and_summarize_2(link, contents, event_data):
   
#    print("scraping...")
   




# @staticmethod
# @slack_events_adapter.on("app_mention")
# def app_mentioned(data):
#   logging.info("app_mention slack event! ", data)

#   user = data['event']['user']
#   channel_id=data['event']['channel']

#   responseText = (f'hi <@{user}>')
#   response =client.chat_postMessage(
#     channel=channel_id,
#     user_id = user,
#     user = user,
#     text = responseText
#   )

if __name__ == "__main__":
  app.run(port=8080)