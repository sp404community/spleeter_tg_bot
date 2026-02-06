# pip install numba
# https://github.com/deezer/spleeter
# https://github.com/tensorflow/tensorflow/issues/54499
import os
#os.environ["CUDA_VISIBLE_DEVICES"]="-1"
import logging
logging.getLogger('tensorflow').disabled = True
import shutil
import aiogram
from aiogram import Bot
from aiogram.bot.api import TelegramAPIServer
from aiogram import Dispatcher, executor, types
from aiogram.utils.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton
import asyncio
#import aiofiles
import spleeter
from spleeter.separator import Separator
import datetime
import json
import aiosqlite
import librosa
from keyfinder import Tonal_Fragment 
from sound_to_midi.monophonic import wave_to_midi
import uuid
import math
import numpy

# https://setiwik.ru/kak-ustanovit-ffmpeg-na-centos-9-stream/
# https://github.com/deezer/spleeter/issues/680
# https://stackoverflow.com/questions/49735693/what-is-the-equivalent-of-this-linux-command-on-windows-cmd
# https://github.com/tdlib/telegram-bot-api?tab=readme-ov-file
# https://unix.stackexchange.com/questions/678777/how-to-get-epel-release-epel-release-next-powertools-in-centos-stream-9
# https://docs.aiogram.dev/en/v2.25.1/telegram/
# https://github.com/tdlib/telegram-bot-api

token=''
local_server = TelegramAPIServer.from_base('http://localhost:8081')
bot=Bot(token=token, server=local_server)
dp = Dispatcher(bot)
cb_walk = CallbackData("id", "action", "chat_id", "message_id", "file_name")
dir_path = os.path.dirname(os.path.realpath(__file__))
stem_type_default = "2" #2,4,5
stem_models = {'2':['vocals','accompaniment'],'4':['bass','drums','vocals','other']}
bot_folder = '/root/telegram-bot-api/bin/{0}'.format(token) # for telegram-bot-api
input_folder = r'{0}/input_file_{1}_stems'.format(dir_path, stem_type_default)
output_folder = r'{0}/output_file_{1}_stems'.format(dir_path, stem_type_default)
midi_folder = r'{0}/midi_output'.format(dir_path)
DB_NAME ="stem_splitter_{0}.db".format(stem_type_default)

with open('messages.json', encoding='utf-8') as json_file:
	base_messages = json.load(json_file)[0]
	
@dp.message_handler(content_types=['audio', 'document']) # list relevant content types
async def process_file(message):
	result = "ok"
	start_time = datetime.datetime.now()
	stem_type = stem_type_default
	
	try:
		file_name = "{0}_{1}.{2}".format(message.chat.id,str(uuid.uuid4().fields[-1])[:6],message.document.file_name[-3:])
		file_name_orig = message.document.file_name
		file_duration = "unknown"
		file_size = message.document.file_size
		file_id = message.document.file_id
		file_unique_id = message.document.file_unique_id
		file_info = await bot.get_file(message.document.file_id)
	except:
		file_name = "{0}_{1}.{2}".format(message.chat.id,str(uuid.uuid4().fields[-1])[:6],message.audio.file_name[-3:])
		file_name_orig = message.audio.file_name
		file_duration = message.audio.duration
		file_size = message.audio.file_size
		file_id = message.audio.file_id
		file_unique_id = message.audio.file_unique_id
		file_info = await bot.get_file(message.audio.file_id)
	print("try to download")
	print(file_info.file_path)
	#await bot.download_file(file_info.file_path, "{0}/{1}".format(input_folder,file_name))
	shutil.copy2(file_info.file_path, "{0}/{1}".format(input_folder, file_name))
	download_time = (datetime.datetime.now()-start_time).total_seconds()
	
	rkm = types.InlineKeyboardMarkup(row_width=3)
	rkm.row(
		InlineKeyboardButton(
			text='\U0001F941 BPM',
			callback_data=cb_walk.new(action="bpm", chat_id=message.chat.id, message_id=message.message_id, file_name=file_name)
		),
		InlineKeyboardButton(
			text='\U0001F3B5 КЛЮЧ',
			callback_data=cb_walk.new(action="key", chat_id=message.chat.id, message_id=message.message_id, file_name=file_name)
		),
		InlineKeyboardButton(
			text='\U0001F3B9 MIDI',
			callback_data=cb_walk.new(action="midi", chat_id=message.chat.id, message_id=message.message_id, file_name=file_name)
		)
	)	
	rkm.row(
		InlineKeyboardButton(
			text='\U0001F39B STEM MP3',
			callback_data=cb_walk.new(action="split_mp3", chat_id=message.chat.id, message_id=message.message_id, file_name=file_name)
		),
		InlineKeyboardButton(
			text='\U0001F39B STEM WAV',
			callback_data=cb_walk.new(action="split_wav", chat_id=message.chat.id, message_id=message.message_id, file_name=file_name)
		)
	)
	await bot.send_message(message.chat.id, "Файл загружен.\nЧто хотите сделать?", parse_mode=types.ParseMode.HTML, reply_markup=rkm, reply_to_message_id=message.message_id)
	
	end_time = datetime.datetime.now()	
	async with aiosqlite.connect(DB_NAME) as db:
		await db.execute(
			'INSERT INTO operations (chat_id, file_name, file_name_orig, file_duration, file_size, file_id, file_unique_id, stem_type, datetime_start, datetime_end, operation, result) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
			(message.chat.id, file_name, file_name_orig, file_duration, file_size, file_id, file_unique_id, stem_type_default, start_time, end_time, 'download', result)
		)
		await db.commit()
	
	###os.remove('{0}/{1}'.format(input_folder, file_name))
	###shutil.rmtree('{0}/{1}'.format(output_folder, file_name[:-4]))
	##return


@dp.callback_query_handler(cb_walk.filter(action='bpm'))
async def bpm_calculate(query: types.CallbackQuery, callback_data: dict):
	await bot.send_message(callback_data['chat_id'], "Определяю <b>BPM</b>...", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
	start_time = datetime.datetime.now()
	
	try:
		result = "ok"
		audio_path = "{0}/{1}".format(input_folder, callback_data['file_name'])
		y, sr = librosa.load(audio_path)
		y_harmonic, y_percussive = librosa.effects.hpss(y)
		tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
		await bot.send_message(callback_data['chat_id'], "<b>BPM: </b>{0}".format(numpy.round(tempo,1)), parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
	except:
		result = "error"
		await bot.send_message(callback_data['chat_id'], "Возникла ошибка с определением <b>BPM</b> - попробуйте позже", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
		
	end_time = datetime.datetime.now()
	
	async with aiosqlite.connect(DB_NAME) as db:
		await db.execute(
			'INSERT INTO operations (chat_id, file_name, file_name_orig, file_duration, file_size, file_id, file_unique_id, stem_type, datetime_start, datetime_end, operation, result) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
			(callback_data['chat_id'], callback_data['file_name'], "", "", "", "", "", stem_type_default, start_time, end_time, 'bpm', result)
		)
		await db.commit()

@dp.callback_query_handler(cb_walk.filter(action='key'))
async def key_calculate(query: types.CallbackQuery, callback_data: dict):
	await bot.send_message(callback_data['chat_id'], "Определяю <b>Тональность/Ключ</b>...", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
	start_time = datetime.datetime.now()
	
	try:
		result = "ok"
		audio_path = "{0}/{1}".format(input_folder, callback_data['file_name'])
		y, sr = librosa.load(audio_path)
		y_harmonic, y_percussive = librosa.effects.hpss(y)
		track = Tonal_Fragment(y_harmonic, sr)
		
		key_message = "<i>Скорее всего:</i> {0} ({1:.1%})".format(max(track.key_dict, key=track.key_dict.get), track.bestcorr)
		if track.altkey is not None:
			key_message = "{0}{1}".format(key_message,"\n<i>Возможно:</i> {0} ({1:.1%})".format(track.altkey, track.altbestcorr))
		del track
	
		await bot.send_message(callback_data['chat_id'], "<b>Ключ: </b>\n{0}".format(key_message), parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
	except:
		result = "error"
		await bot.send_message(callback_data['chat_id'], "Возникла ошибка с определением <b>Ключа</b> - попробуйте позже", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
		
	end_time = datetime.datetime.now()
	
	async with aiosqlite.connect(DB_NAME) as db:
		await db.execute(
			'INSERT INTO operations (chat_id, file_name, file_name_orig, file_duration, file_size, file_id, file_unique_id, stem_type, datetime_start, datetime_end, operation, result) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
			(callback_data['chat_id'], callback_data['file_name'], "", "", "", "", "", stem_type_default, start_time, end_time, 'key', result)
		)
		await db.commit()

@dp.callback_query_handler(cb_walk.filter(action='midi'))
async def midi_convert(query: types.CallbackQuery, callback_data: dict):
	await bot.send_message(callback_data['chat_id'], "Конвертирую в <b>MIDI</b>...", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
	start_time = datetime.datetime.now()
	
	try:
		result = "ok"
		audio_path = "{0}/{1}".format(input_folder, callback_data['file_name'])
		y, sr = librosa.load(audio_path)
		midi = wave_to_midi(y, sr)
		
		with open ("{0}/{1}.midi".format(midi_folder, callback_data['file_name'][:-4]), 'wb') as f:
			midi.writeFile(f)
		
		with open ("{0}/{1}.midi".format(midi_folder, callback_data['file_name'][:-4]), 'rb') as midi_file:
			await bot.send_document(callback_data['chat_id'], midi_file, reply_to_message_id=callback_data['message_id'])
	except:
		result = "error"
		await bot.send_message(callback_data['chat_id'], "Возникла ошибка с конвертацией в <b>MIDI</b> - попробуйте позже", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
		
	end_time = datetime.datetime.now()
	
	async with aiosqlite.connect(DB_NAME) as db:
		await db.execute(
			'INSERT INTO operations (chat_id, file_name, file_name_orig, file_duration, file_size, file_id, file_unique_id, stem_type, datetime_start, datetime_end, operation, result) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
			(callback_data['chat_id'], "{0}.{1}".format(callback_data['file_name'][:-4],'midi'), "", "", "", "", "", stem_type_default, start_time, end_time, 'midi', result)
		)
		await db.commit()

@dp.callback_query_handler(cb_walk.filter(action='split_mp3'))
async def stem_split_mp3(query: types.CallbackQuery, callback_data: dict):
	await bot.send_message(callback_data['chat_id'], "Начинаю разделение на <b>стэмы (в mp3)</b>...", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
	start_time = datetime.datetime.now()
	
	try:
		result = "ok"
		stem_type = stem_type_default
		separator.separate_to_file("{0}/{1}".format(input_folder, callback_data['file_name']), output_folder, codec="mp3", bitrate="320k")
		
		await bot.send_message(callback_data['chat_id'], "Обработка закончена.\nЗагружаю стэмы...", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
		try:
			for instrument in stem_models[stem_type]:
				print('Отправка {0}/{1}/{2}.mp3'.format(output_folder, callback_data['file_name'][:-4], instrument))
				stem = open('{0}/{1}/{2}.mp3'.format(output_folder, callback_data['file_name'][:-4], instrument), 'rb')
				await bot.send_document(callback_data['chat_id'], stem, reply_to_message_id=callback_data['message_id'])
		except:
			await bot.send_message(callback_data['chat_id'], "Обработанный файл стэма слишком большой или возникла ошибка.\nПовторите позднее.", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
			result = "error_upload"
	except:
		result = "error_convert"
		await bot.send_message(callback_data['chat_id'], "Возникла ошибка с конвертацией.\nПовторите позднее.", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])

	end_time = datetime.datetime.now()
	
	async with aiosqlite.connect(DB_NAME) as db:
		await db.execute(
			'INSERT INTO operations (chat_id, file_name, file_name_orig, file_duration, file_size, file_id, file_unique_id, stem_type, datetime_start, datetime_end, operation, result) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
			(callback_data['chat_id'], callback_data['file_name'], "", "", "", "", "", stem_type_default, start_time, end_time, 'split_mp3', result)
		)
		await db.commit()

@dp.callback_query_handler(cb_walk.filter(action='split_wav'))
async def stem_split_wav(query: types.CallbackQuery, callback_data: dict):
	await bot.send_message(callback_data['chat_id'], "Начинаю разделение на <b>стэмы (в wav)</b>...", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
	start_time = datetime.datetime.now()
	
	try:
		result = "ok"
		stem_type = stem_type_default
		separator.separate_to_file("{0}/{1}".format(input_folder, callback_data['file_name']), output_folder)
		
		await bot.send_message(callback_data['chat_id'], "Обработка закончена.\nЗагружаю стэмы...", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
		try:
			for instrument in stem_models[stem_type]:
				print('Отправка {0}/{1}/{2}.wav'.format(output_folder, callback_data['file_name'][:-4], instrument))
				stem = open('{0}/{1}/{2}.wav'.format(output_folder, callback_data['file_name'][:-4], instrument), 'rb')
				await bot.send_document(callback_data['chat_id'], stem, reply_to_message_id=callback_data['message_id'])
		except:
			await bot.send_message(callback_data['chat_id'], "Обработанный файл стэма слишком большой или возникла ошибка.\nПовторите позднее.", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])
			result = "error_upload"
	except:
		result = "error_convert"
		await bot.send_message(callback_data['chat_id'], "Возникла ошибка с конвертацией.\nПовторите позднее.", parse_mode=types.ParseMode.HTML, reply_to_message_id=callback_data['message_id'])

	end_time = datetime.datetime.now()
	
	async with aiosqlite.connect(DB_NAME) as db:
		await db.execute(
			'INSERT INTO operations (chat_id, file_name, file_name_orig, file_duration, file_size, file_id, file_unique_id, stem_type, datetime_start, datetime_end, operation, result) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
			(callback_data['chat_id'], callback_data['file_name'], "", "", "", "", "", stem_type_default, start_time, end_time, 'split_mp3', result)
		)
		await db.commit()
		

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
	await bot.send_message(message.chat.id, base_messages['start'], parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['faq'])
async def faq(message: types.Message):
	await bot.send_message(message.chat.id, base_messages['faq'], parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['info'])
async def info(message: types.Message):
	await bot.send_message(message.chat.id, base_messages['info'], parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands=['bp'])
async def info(message: types.Message):
	try:
		params = message.text.split(" ")
		await bot.send_message(message.chat.id, "<b>Pitch:</b> {0}".format(round(math.log((float(params[2])/float(params[1])),2)*12,2)), parse_mode=types.ParseMode.HTML)
	except:
		await bot.send_message(message.chat.id, 'Попробуйте ввести команду так\n/bp 95 120\nили\n/bp 134.2 62.5', parse_mode=types.ParseMode.HTML)


if __name__ == '__main__':
	separator = Separator('spleeter:{0}stems'.format(stem_type_default))
	executor.start_polling(dp, skip_updates=True)
