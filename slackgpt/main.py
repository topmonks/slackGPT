import openai
import tiktoken
from openai import ChatCompletion
from slack_bolt.app.async_app import AsyncApp
from slack_sdk import WebClient

from .cfg import *


def _init_logging():
    logger = logging.getLogger(__name__)
    str_handler = logging.StreamHandler()
    log_format = logging.Formatter(
        '%(asctime)s : %(levelname)s : %(message)s'
    )
    str_handler.setFormatter(log_format)
    logger.addHandler(str_handler)
    if LOG_FILE:
        f_handler = logging.FileHandler(LOG_FILE)
        f_handler.setFormatter(log_format)
        logger.addHandler(f_handler)

    logger.setLevel(LOG_LEVEL)

    return logger


log = _init_logging()


class Conversation:
    GPT_ROLE_ASSISTANT = 'assistant'  # message added by the chatbot
    GPT_ROLE_USER = 'user'  # message added by the user
    GPT_ROLE_SYSTEM = 'system'  # "fine-tuning" message

    def __init__(self, user, channel, gpt_version='gpt-3.5-turbo'):
        self._user = user
        self._channel = channel
        self._gpt_version = gpt_version

        self._client = WebClient(token=SLACK_BOT_TOKEN)
        self._history = []
        self._is_prompt_in_prg = False
        self._max_tokens = 2000
        self._temperature = 1.0

    def start(self):
        self.post_msg("> New Conversation Started")

    def finish(self):
        self.post_msg("> Conversation Finished")

    def add_sys_content(self, text):
        self._history.insert(0, {'role': self.GPT_ROLE_SYSTEM, 'content': text})
        log.info(
            'System Content added, user=%s, content=%s' % (
                self._user, text
            )
        )

    def add_message(self, text, retries=0):
        if not self._is_prompt_in_prg:
            self._is_prompt_in_prg = True

            if retries == 0:
                self._history.append(
                    {'role': self.GPT_ROLE_USER, 'content': text}
                )
                tc, mc = self._inform_token_usage()
                log.info(
                    'Prompt inserted: user=%s, text=%s, '
                    'token_count=%d, max_token_count=%d' % (
                        self._user, text, tc, mc
                    )
                )

            try:
                completion = ChatCompletion.create(
                    model=self._gpt_version,
                    messages=self._history,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens
                )
                gpt_response = completion['choices'][0]['message']['content']
                self._history.append(
                    {'role': self.GPT_ROLE_ASSISTANT, 'content': gpt_response}
                )
                log.info('ChatGPT Response: user=%s, text=%s' % (
                    self._user, gpt_response
                ))
                self.post_msg(gpt_response)
                self._is_prompt_in_prg = False
            except Exception as e:
                log.error('GPT Error: %s, retries=%d' % (e, retries))
                if retries < CHAT_GPT_ERROR_RETRIES:
                    self._is_prompt_in_prg = False
                    self.add_message(text, retries + 1)
                else:
                    log.error("Unable to prompt ChatGPT, Max Retries Reached.")
                    self.post_msg(
                        'Sorry, We were unable to reach the ChatGPT service; '
                        'GptError=%s' % e
                    )
                    self._is_prompt_in_prg = False
        else:
            self.post_msg("Please wait until your previous prompt is finished")

    def set_temperature(self, t):
        if t < 0:
            t = 0.0
        elif t > 2:
            t = 2.0

        self._temperature = t

        log.info('Temperature set, user=%s, temp=%f' % (self._user, t))

    def set_max_tokens(self, val):
        if val < 5:
            val = 5
        elif val > 4000:
            val = 4000

        self._max_tokens = val

        log.info('Max Tokens set, user=%s, max_tokens=%d' % (self._user, val))

    def post_settings(self):
        sys_content = []
        for m in self._history:
            if m['role'] == self.GPT_ROLE_SYSTEM:
                sys_content.append(m['content'])

        tc, mc = self._inform_token_usage(False)

        msg = 'sys_content=%s, token_count=%s, max_token_count=%s, ' \
              'temperature=%s, max_tokens=%s' % (
                  str(sys_content), tc, mc, self._temperature, self._max_tokens
              )

        self.post_msg(msg)

    def post_msg(self, msg, retries=0):
        try:
            self._client.chat_postMessage(channel=self._user, text=msg)
        except Exception:
            if retries < SLACK_ERROR_RETRIES:
                log.error("Unable to send slack message, retrying...")
                self.post_msg(msg, retries + 1)
            else:
                log.error("We were unable to ")

    def _inform_token_usage(self, do_post=True):
        curr_tokens = self._get_token_count(self._history)
        max_tokens = MAX_TOKEN_COUNT[self._gpt_version]
        if do_post:
            self.post_msg(
                'token_usage: %d/%d (+ Number of tokens in the answer, '
                'decrease max_tokens if problems occurs)' % (
                    curr_tokens, max_tokens
                )
            )

        return curr_tokens, max_tokens

    def _get_token_count(self, msgs):
        encoding = tiktoken.encoding_for_model(self._gpt_version)
        token_count = 0
        for m in msgs:
            token_count += len(encoding.encode(m['content']))
        return token_count


class SlackGPT(object):
    
    CMD_CONVERSATION_MK = '\\start'
    CMD_CONVERSATION_RM = '\\end'
    CMD_SYS_ROLE_MK = '\\sys_role'
    CMD_TEMPERATURE_SET = '\\temp_set'
    CMD_MAX_TOKENS_SET = '\\max_tokens_set'
    CMD_SETTINGS_GET = '\\settings_get'

    def __init__(self):
        if not self._check_secrets():
            log.error(
                'You need to provide all secrets from the environment'
                '(SLACK_BOT_TOKEN, SLACK_BOT_SIGN_SECRET, OPENAI_API_KEY)'
            )
            exit(1)

        self._slack = AsyncApp(
            token=SLACK_BOT_TOKEN,
            signing_secret=SLACK_BOT_SIGN_SECRET
        )

        openai.api_key = OPENAI_API_KEY
        self._register_handlers()
        self._conversations = {}
        self._app_stopping = False

    def start(self):
        log.info('App Started...')
        self._slack.start(port=PORT)

    def stop(self):
        # Never actually called, signals are handled by retarded Slack app
        log.info('App Stopping...')
        self._app_stopping = True
        exit(0)

    def _register_handlers(self):
        @self._slack.event("message")
        async def handle_message(body, say, logger):
            if not self._app_stopping:
                if 'user' in body['event']:
                    text = body['event']['text']
                    channel = body['event']['channel']
                    user = body['event']['user']
                    channel_type = body['event']['channel_type']

                    if channel_type == SLACK_CHANNEL_TYPE_IM:
                        # Create new Conversation
                        if text == self.CMD_CONVERSATION_MK:
                            self._check_rm_conversation(user)
                            self._create_new_conversation(user, channel)
                        # Finish Conversation
                        elif text == self.CMD_CONVERSATION_RM:
                            self._check_rm_conversation(user)
                        # Set System role
                        elif text.startswith(self.CMD_SYS_ROLE_MK):
                            self._conv_set_sys_role(user, channel, text)
                        # Set Temperature
                        elif text.startswith(self.CMD_TEMPERATURE_SET):
                            self._conv_set_temperature(user, channel, text)
                        # Set Max Tokens
                        elif text.startswith(self.CMD_MAX_TOKENS_SET):
                            self._conv_set_max_tokens(user, channel, text)
                        # Get Settings
                        elif text == self.CMD_SETTINGS_GET:
                            self._conv_get_settings(user, channel)
                        # Make ChatGPT Request
                        else:
                            self._conv_mk_chatgpt_request(user, channel, text)

    def _conv_get_settings(self, user, channel):
        conversation = self._conv_check_mk(user, channel)
        conversation.post_settings()

    def _conv_set_sys_role(self, user, channel, text):
        conversation = self._conv_check_mk(user, channel)
        conversation.add_sys_content(
            text.split(self.CMD_SYS_ROLE_MK)[1].strip()
        )

    def _conv_set_max_tokens(self, user, channel, text):
        conversation = self._conv_check_mk(user, channel)
        try:
            conversation.set_max_tokens(
                int(text.split(self.CMD_MAX_TOKENS_SET)[1].strip())
            )
        except Exception:
            log.info(
                'Unable to set max tokens for user %s, value=%s' % (user, text)
            )
            conversation.post_msg(
                'Unable to set max tokens, invalid value: %s' % text
            )

    def _conv_set_temperature(self, user, channel, text):
        conversation = self._conv_check_mk(user, channel)
        try:
            conversation.set_temperature(
                float(text.split(self.CMD_TEMPERATURE_SET)[1].strip())
            )
        except Exception:
            log.info(
                'Unable to set temperature for user %s, value=%s' % (user, text)
            )
            conversation.post_msg(
                'Unable to set temperature, invalid value: %s' % text
            )

    def _conv_mk_chatgpt_request(self, user, channel, text):
        conversation = self._conv_check_mk(user, channel)
        conversation.add_message(text)

    def _conv_check_mk(self, user, channel):
        if user in self._conversations.keys():
            conversation = self._conversations[user]
        else:
            conversation = self._create_new_conversation(user, channel)

        return conversation

    def _create_new_conversation(self, user, channel):
        conversation = Conversation(user, channel)
        self._conversations[user] = conversation
        conversation.start()
        log.info('Conversation for user %s started' % user)
        return conversation

    def _check_rm_conversation(self, user):
        if user in self._conversations.keys():
            conversation = self._conversations[user]
            conversation.finish()
            del self._conversations[user]
            log.info('Conversation for user %s finished' % user)

    @staticmethod
    def _check_secrets():
        return SLACK_BOT_TOKEN and SLACK_BOT_SIGN_SECRET and OPENAI_API_KEY
