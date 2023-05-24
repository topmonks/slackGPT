# SlackGPT

## Abstract

Introducing the ChatGPT integration for Slack Messaging Application. As a 
dedicated Slack Application, users can seamlessly communicate with it through 
private messages. This feature-packed integration enables users to adjust 
ChatGPT system_role content, temperature, and response max tokens, all within 
the familiar Slack interface. Additionally, it keeps users informed about 
current token usage. Experience effortless collaboration and streamlined 
communication with ChatGPT and Slack.

## Installation 

1) Create a Slack Application (use slack_manifest.yml file)
2) Set proper settings.event_subscription.request_url, depending on our server 
setup (You can use ngrok service for local testing)
3) Install the SlackGPT service via python pip (and virtualenv) or use docker
and provided Dockerfile
4) You need to provide necessary secret keys, see **.env_example** file  

## Usage

You can interact with the SlackGPT App via following commands:

* **\start** - Starts the new conversation, and ends the former one if exists. (this
is not necessarily needed, you can just start prompting)
* **\end** - Ends the current conversation, if exists.
* **\sys_role content** - Add ChatGPT System Role for current conversation.
* **\temp_set (0.0 - 2.0, default=1.0)** - Set Model Temperature for current 
conversation
* **\max_tokens_set (5 - 4000, default=800)** - Set Maximum Number of Tokens that
the response should have.
* **\settings_get** - Return the Settings for current conversation.
* Any other text acts as a prompt for ChatGPT