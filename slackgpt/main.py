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
        self._post_msg(">>> NEW CONVERSATION STARTED")

    def finish(self):
        self._post_msg(">>> CONVERSATION FINISHED")

    def add_sys_content(self, text):
        self._history.insert(0, {'role': 'system', 'content': text})
        log.info(
            'System Content added, user=%s, content=%s' % (
                self._user, text
            )
        )

    def add_message(self, text, retries=0):
        if not self._is_prompt_in_prg:
            self._is_prompt_in_prg = True

            if retries == 0:
                self._history.append({'role': 'user', 'content': text})
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
                    {'role': 'assistant', 'content': gpt_response}
                )
                log.info('ChatGPT Response: user=%s, text=%s' % (
                    self._user, gpt_response
                ))
                self._post_msg(gpt_response)
                self._is_prompt_in_prg = False
            except Exception as e:
                log.error('GPT Error: %s, retries=%d' % (e, retries))
                if retries < CHAT_GPT_ERROR_RETRIES:
                    self._is_prompt_in_prg = False
                    self.add_message(text, retries + 1)
                else:
                    log.error("Unable to prompt ChatGPT, Max Retries Reached.")
                    self._post_msg(
                        'Sorry, We were unable to reach the ChatGPT service; '
                        'GptError=%s' % e
                    )
                    self._is_prompt_in_prg = False
        else:
            self._post_msg("Please wait until your previous prompt is finished")

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

    def _inform_token_usage(self):
        curr_tokens = self._get_token_count(self._history)
        max_tokens = MAX_TOKEN_COUNT[self._gpt_version]
        self._post_msg('token_usage: %d/%d' % (curr_tokens, max_tokens))
        return curr_tokens, max_tokens

    def _get_token_count(self, msgs):
        encoding = tiktoken.encoding_for_model(self._gpt_version)
        token_count = 0
        for m in msgs:
            token_count += len(encoding.encode(m['content']))
        return token_count

    def _post_msg(self, msg, retries=0):
        try:
            self._client.chat_postMessage(channel=self._user, text=msg)
        except Exception:
            if retries < SLACK_ERROR_RETRIES:
                log.error("Unable to send slack message, retrying...")
                self._post_msg(msg, retries + 1)
            else:
                log.error("We were unable to ")


class SlackGPT(object):
    CMD_CONVERSATION_MK = '\\start'
    CMD_CONVERSATION_RM = '\\end'
    CMD_SYS_ROLE_MK = '\\sys_role'
    CMD_TEMPERATURE_SET = '\\temp_set'
    CMD_MAX_TOKENS_SET = '\\max_tokens_set'

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
        self._slack.start()

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
                            if user in self._conversations.keys():
                                conversation = self._conversations[user]
                                conversation.add_sys_content(
                                    text.split(self.CMD_SYS_ROLE_MK)[1].
                                    strip()
                                )
                            else:
                                conversation = \
                                    self._create_new_conversation(
                                        user, channel
                                    )
                                conversation.add_sys_content(
                                    text.split(self.CMD_SYS_ROLE_MK)[1].
                                    strip()
                                )

                        # Set Temperature
                        elif text.startswith(self.CMD_TEMPERATURE_SET):
                            if user in self._conversations.keys():
                                conversation = self._conversations[user]
                                try:
                                    conversation.set_temperature(
                                        float(
                                            text.split(
                                                self.CMD_TEMPERATURE_SET
                                            )[1].strip()
                                        )
                                    )
                                except Exception:
                                    # Parse error
                                    pass
                            else:
                                conversation = \
                                    self._create_new_conversation(
                                        user, channel
                                    )
                                try:
                                    conversation.set_temperature(
                                        float(
                                            text.split(
                                                self.CMD_TEMPERATURE_SET)[1].
                                            strip()
                                        )
                                    )
                                except Exception:
                                    # Parse error
                                    pass

                        # Set Max Tokens
                        elif text.startswith(self.CMD_MAX_TOKENS_SET):
                            if user in self._conversations.keys():
                                conversation = self._conversations[user]
                                try:
                                    conversation.set_max_tokens(
                                        int(
                                            text.split(
                                                self.CMD_MAX_TOKENS_SET
                                            )[1].strip()
                                        )
                                    )
                                except Exception:
                                    # Parse error
                                    pass
                            else:
                                conversation = \
                                    self._create_new_conversation(
                                        user, channel
                                    )
                                try:
                                    conversation.set_max_tokens(
                                        int(
                                            text.split(
                                                self.CMD_MAX_TOKENS_SET
                                            )[1].strip()
                                        )
                                    )
                                except Exception:
                                    # Parse error
                                    pass

                        # Make ChatGPT Request
                        else:
                            if user in self._conversations.keys():
                                conversation = self._conversations[user]
                                conversation.add_message(text)
                            else:
                                conversation = \
                                    self._create_new_conversation(
                                        user, channel
                                    )
                                conversation.add_message(text)

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
