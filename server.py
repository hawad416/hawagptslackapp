import os
from flask import Flask
from slack_sdk import WebClient 
from slackeventsapi import SlackEventAdapter

app = Flask(__name__)

slack_token = os.environ.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
client = WebClient(token=slack_token)

print(SLACK_SIGNING_SECRET)
print((slack_token))

## why do we need the route + other stuff
@app.route("/")
def hello():
  return "VANI IS AMAZING!"

response = client.chat_postMessage(
    				channel="slacktest",
    				text="hi hawa!!")
	
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

@app.route('/testroute')
def ok():
  print("hawa")
  return "[]"


if __name__ == "__main__":
  app.run(port=8080)