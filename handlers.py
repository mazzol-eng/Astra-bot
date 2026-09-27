"""Seis fluxos; solicitações reais são encaminhadas ao chat da equipe configurado.

Estado de conversa é volátil. Não há pagamento, estoque ou agenda integrados.
Logs registram eventos e tamanhos, não conteúdo pessoal nem tokens.
"""
import logging
import secrets
import time

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from telegram.error import TelegramError

log = logging.getLogger(__name__)
FLOWS = {
    'pedido': ('🛍 Fazer pedido', 'Informe o produto e a quantidade. Catálogo de exemplo: camiseta Astra — R$ 79; caneca Astra — R$ 39. A equipe confirma estoque, frete e pagamento.'),
    'suporte': ('🛠 Suporte', 'Descreva seu problema em uma mensagem. Não envie senhas, dados de cartão ou documentos.'),
    'faq': ('💬 Dúvidas frequentes', ''),
    'agendamento': ('📅 Agendamento', 'Qual dia, horário e assunto você prefere para uma conversa? É uma solicitação: a equipe precisa confirmar a disponibilidade.'),
    'orcamento': ('📝 Orçamento', 'Conte o que você precisa, quantidade e prazo desejado. Não envie dados sensíveis.'),
    'humano': ('👋 Falar com a equipe', 'Conte brevemente o assunto. A equipe recebe sua solicitação e responde pelo Telegram quando estiver disponível.'),
}
FAQ = {
    'horario': 'Horário de exemplo: segunda a sexta, das 9h às 18h (horário de Brasília). O bot responde automaticamente enquanto o servidor estiver ativo.',
    'pagamento': 'Pagamento é combinado diretamente com a equipe após a confirmação do pedido. O bot não cobra e não solicita dados de cartão.',
    'prazo': 'O prazo e o frete são informados pela equipe conforme o produto e o destino. Nenhum prazo de entrega é garantido nesta configuração de exemplo.',
}


def menu():
    entries = [Button(label, callback_data='flow:' + key) for key, (label, _) in FLOWS.items()]
    return Markup([entries[i:i + 2] for i in range(0, len(entries), 2)])


def back():
    return Markup([[Button('← Menu principal', callback_data='menu')]])


async def send(update, context, text, markup=None):
    try:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=markup)
        log.info('resposta_enviada chat=%s caracteres=%s', update.effective_chat.id, len(text))
        return True
    except TelegramError as exc:
        log.warning('falha_resposta tipo=%s', type(exc).__name__)
        return False


def received(update, event):
    log.info('evento_recebido evento=%s chat=%s caracteres=%s', event,
             update.effective_chat.id, len(update.effective_message.text or '') if update.effective_message else 0)


async def private_only(update, context):
    if update.effective_chat.type != 'private':
        await send(update, context, 'Para proteger seus dados, abra uma conversa privada comigo e envie /start.')
        return False
    return True


async def start(update, context):
    received(update, 'start')
    if not await private_only(update, context):
        return
    context.user_data.clear()
    await send(update, context, 'Olá! Eu sou o Astra ✨ Seu assistente de atendimento.\nComo posso ajudar?\n\nEnviamos solicitações à equipe somente após sua confirmação. Use /cancelar a qualquer momento.', menu())


async def help_command(update, context):
    received(update, 'help')
    await send(update, context, '/start — abrir os seis serviços\n/help — ver ajuda\n/cancelar — apagar o rascunho e voltar\n/meuid — ver seu ID para configuração\n\nPedidos, suporte, dúvidas, agendamento, orçamento e contato humano. Não processamos pagamentos nem confirmamos reservas automaticamente.', menu())


async def whoami(update, context):
    if await private_only(update, context):
        await send(update, context, f'Seu ID: {update.effective_chat.id}\nSe você administra este bot, use esse número em ADMIN_CHAT_ID no servidor. Não envie seu token por aqui.')


async def cancel(update, context):
    context.user_data.clear()
    await send(update, context, 'Rascunho cancelado. Como posso ajudar?', menu())


async def callback(update, context):
    query = update.callback_query
    try:
        await query.answer()  # answerCallbackQuery: encerra o carregamento do botão.
    except TelegramError as exc:
        log.warning('falha_callback tipo=%s', type(exc).__name__)
        return  # botão expirado não deve disparar uma solicitação antiga.
    received(update, 'callback')
    if not await private_only(update, context):
        return
    data = query.data or ''
    if data == 'menu':
        await cancel(update, context)
    elif data.startswith('flow:') and data[5:] in FLOWS:
        flow = data[5:]
        context.user_data.clear()
        if flow == 'faq':
            await send(update, context, 'O que você gostaria de saber?', Markup([
                [Button('Horários', callback_data='faq:horario'), Button('Pagamento', callback_data='faq:pagamento')],
                [Button('Prazos e entrega', callback_data='faq:prazo')],
                [Button('← Menu principal', callback_data='menu')]]))
        elif not context.bot_data['settings'].admin_chat_id:
            await send(update, context, FLOWS[flow][1] + '\n\n⚠️ A equipe ainda não foi configurada. Este canal não recebe solicitações por enquanto. Administrador: configure ADMIN_CHAT_ID.', back())
        else:
            context.user_data.update(flow=flow, expires=time.time() + 1800)
            await send(update, context, FLOWS[flow][1], back())
    elif data.startswith('faq:') and data[4:] in FAQ:
        await send(update, context, FAQ[data[4:]], back())
    elif data.startswith('confirm:'):
        draft = context.user_data.get('draft')
        if not draft or data != 'confirm:' + draft['id'] or time.time() > context.user_data.get('expires', 0):
            await send(update, context, 'Esta confirmação expirou ou já foi usada. Comece novamente com /start.', menu())
            return
        # Consome antes de enviar: clique duplo não encaminha duas vezes.
        context.user_data.clear()
        user = update.effective_user
        contact = f'@{user.username}' if user.username else f'ID {user.id} (sem usuário público)'
        message = (f"Astra • solicitação {draft['id']}\nServiço: {FLOWS[draft['flow']][0]}\n"
                   f"Cliente: {user.full_name}\nContato: {contact}\nID: {user.id}\n\n{draft['text']}\n\n"
                   'Aguardando avaliação humana. Se não houver @ público, peça ao cliente que configure um para facilitar o retorno.')
        try:
            await context.bot.send_message(chat_id=context.bot_data['settings'].admin_chat_id, text=message)
            log.info('solicitacao_encaminhada referencia=%s fluxo=%s', draft['id'], draft['flow'])
        except TelegramError as exc:
            log.warning('falha_encaminhamento tipo=%s referencia=%s', type(exc).__name__, draft['id'])
            await send(update, context, f"Não consegui confirmar o envio da solicitação {draft['id']}. Pode ter ocorrido uma falha de conexão. Confira com a equipe antes de reenviar para evitar duplicidade.", menu())
            return
        await send(update, context, f"Solicitação {draft['id']} enviada à equipe ✅\nIsso não confirma compra, pagamento ou reserva. Aguarde o retorno humano. Você pode abrir outra solicitação pelo menu.", menu())
    else:
        await send(update, context, 'Essa opção não está disponível. Escolha uma opção atual.', menu())


async def text_message(update, context):
    received(update, 'texto')
    if not await private_only(update, context):
        return
    flow = context.user_data.get('flow')
    if not flow:
        await send(update, context, 'Não entendi 🤔 Digite /help para ver as opções ou escolha abaixo.', menu())
        return
    if time.time() > context.user_data.get('expires', 0):
        context.user_data.clear()
        await send(update, context, 'Sua sessão expirou após 30 minutos. Escolha o serviço novamente.', menu())
        return
    text = update.message.text.strip()
    if not 3 <= len(text) <= 1500:
        await send(update, context, 'Envie entre 3 e 1.500 caracteres, sem informações sensíveis.')
        return
    ref = secrets.token_hex(4).upper()
    context.user_data['draft'] = {'id': ref, 'flow': flow, 'text': text}
    await send(update, context, f"Confira sua solicitação:\n\n{text}\n\nAo confirmar, o texto, seu nome e seu contato do Telegram serão enviados à equipe. Deseja enviar?", Markup([
        [Button('Confirmar envio', callback_data='confirm:' + ref)],
        [Button('Cancelar', callback_data='menu')]]))


async def unknown_command(update, context):
    await send(update, context, 'Comando não reconhecido. Digite /help para ver os comandos disponíveis.')


async def error_handler(update, context):
    # Não registra exception/traceback bruto: pode conter token ou dados do cliente.
    log.error('erro_nao_tratado tipo=%s', type(context.error).__name__)
    if update and getattr(update, 'effective_chat', None):
        await send(update, context, 'Ops, ocorreu um problema temporário. Tente /start novamente.')
