#!/usr/bin/env python
# coding: utf-8

# In[25]:


import telebot
import pymongo
import datetime
from bson.binary import Binary
from bson.objectid import ObjectId


# In[26]:


token = '1317990069:AAHkp9-VAqzM9DFvGYPe-7D8ax6RxgVHGDU'
mongo_db_password = 'PXl99yejoNX9OBK3'
mongo_db_user = 'hse'


# In[27]:


bot = telebot.TeleBot(token)


# In[28]:


client = pymongo.MongoClient('mongodb+srv://hse:PXl99yejoNX9OBK3@cluster0.rqg7u.mongodb.net/fitness_bot?retryWrites=true&w=majority')
db = client.fitness_bot


# In[29]:


bot = telebot.TeleBot(token, threaded = False)

# all bot messages
MESSAGES = {
    'schedule': '\U0001F5D3 Расписание',
    'instructors': '\U0001F3CB Тренеры',
    'location': '\U0001F4CD Локация',
    'signup': '\U0000270F Записаться на тренировку',
    
    'weekdays': {
        'monday': 'Понедельник',
        'tuesday': 'Вторник',
        'wednesday': 'Среда',
        'thursday': 'Четверг',
        'friday': 'Пятница',
        'saturday': 'Суббота',
        'sunday': 'Воскресенье',
    },
}

# main bot keyboard layout
DEFAULT_KEYBOARD = telebot.types.ReplyKeyboardMarkup(one_time_keyboard = False) # create reply keyboard
DEFAULT_KEYBOARD.row(MESSAGES['schedule'])
DEFAULT_KEYBOARD.row(MESSAGES['signup'])
DEFAULT_KEYBOARD.row(MESSAGES['instructors'])
DEFAULT_KEYBOARD.row(MESSAGES['location'])


# In[30]:


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# In[31]:


# asks user to select menu action
@bot.message_handler(commands = ['start'])
def startHandler(message):    
    bot.send_message(
        message.chat.id,
        '*Выберите действие в меню*',
        reply_markup = DEFAULT_KEYBOARD,
        parse_mode = 'markdown',
    )


# In[32]:


# asks user to select the day to show schedule 
@bot.message_handler(func = lambda message: message.text == MESSAGES['schedule'])
def scheduleHandler(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(one_time_keyboard = True)

    for i in MESSAGES['weekdays'].values():
        keyboard.row(i)
    
    msg = bot.send_message(
        message.chat.id,
        'Выберите день:', 
        reply_markup = keyboard,
        parse_mode = 'markdown',
    )
    bot.register_next_step_handler(msg, sendSchedule)

# showing schedule for a particular (chosen) day
def sendSchedule(message):
    day = [day_key for day_key in MESSAGES['weekdays'].keys() if MESSAGES['weekdays'][day_key] == message.text][0]
    string = ''
    d = db.schedule.find_one({'day_name': day})
    
    for workout in d['workouts']:
        time_from = workout['time']['from']
        time_to = workout['time']['to']
        name = workout['name']
        instructor = db.instructors.find_one({ 'id': workout['instructor_id'] })
        instructor = instructor['name'] + " " + instructor['lastname']
        string += "{} - {}: {} ({})\n".format(time_from, time_to, name, instructor)
    bot.send_message(
        message.chat.id,
        'Расписание на {}:\n'.format(message.text.lower()) + string,
        reply_markup = DEFAULT_KEYBOARD,
    )


# In[33]:


# select instructor's image from database based on id
def getInstructorMessage(index):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row_width = 3
    amount = db.instructors.count_documents({})
    if index < 0:
        index = amount - 1
    elif index >= amount:
        index = 0
    
    instructor = db.instructors.find_one({}, skip = index)
    instructor_image = db.instructors_images.find_one({'instructor_id': instructor['id']})['image']
    button_list = [
        { 'icon': '\U00002B05', 'data': 'prev'},
        { 'icon': '{} из {}'.format(index + 1, amount), 'data': 'next'},
        { 'icon': '\U000027A1', 'data': 'next'},
    ]
    
    markup.add(
        telebot.types.InlineKeyboardButton(
            text=button_list[0]['icon'],
            callback_data='instructor|action,{},current,{}'.format(button_list[0]['data'], index)
        ),
        telebot.types.InlineKeyboardButton(
            text=button_list[1]['icon'],
            callback_data='instructor|action,{},current,{}'.format(button_list[1]['data'], index)
        ),
        telebot.types.InlineKeyboardButton(
            text=button_list[2]['icon'],
            callback_data='instructor|action,{},current,{}'.format(button_list[2]['data'], index)
        ),
    )
    return {
        'keyboard': markup,
        'instructor': instructor_image,
    }
    
# showing first image with instructor descriptions 
@bot.message_handler(func = lambda message: message.text == MESSAGES['instructors'])
def instructorHandler(message):    
    new_message = getInstructorMessage(0)
    
    msg = bot.send_photo(
        message.chat.id,
        new_message['instructor'], 
        reply_markup = new_message['keyboard'],
        parse_mode = 'markdown',
    )

# removes previous instructor's image and shows next one
@bot.callback_query_handler(func=lambda data: data.data.startswith('instructor|'))
def loadNextInstructor(call):
    bot.delete_message(call.message.chat.id, call.message.id)
    data = call.data.split('|')[1].split(',')
    data = list(chunks(data, 2))
    data = dict([(pair[0], pair[1]) for pair in data])

    index = int(data['current']) + 1 if data['action'] == 'next' else int(data['current']) - 1
    new_message = getInstructorMessage(index)
    
    msg = bot.send_photo(
        call.message.chat.id,
        new_message['instructor'], 
        reply_markup = new_message['keyboard'],
        parse_mode = 'markdown',
    )


# In[34]:


# sends location to user
@bot.message_handler(func = lambda message: message.text == MESSAGES['location'])
def locationHandler(message):
    keyboard = telebot.types.ReplyKeyboardMarkup() 
    bot.send_message(
        message.chat.id,
        'Мы находимся по адресу Аптекарский проспект, 16. Карта: ', 
        reply_markup = keyboard,
        parse_mode = 'markdown',
    )
    bot.send_location(message.chat.id, 59.972964384661424, 30.3194619221117) 


# In[35]:


# returns all workouts for chosen day or creates ampty workouts if there is no workouts for the day yet in the database
def getWorkoutDay(week_day, date):
    workouts = list(db.workouts.find({ 'date': date }))

    if len(workouts) == 0:
         return createWorkoutDay(week_day, date)
   
    return workouts

# creates workouts for chosen day based on existing schedule
def createWorkoutDay(week_day, date):
    workouts = db.schedule.find_one({ 'day_name': week_day })['workouts']
    workouts = [
        {
            'time': {
                'from': workout['time']['from'],
                'to': workout['time']['to'],
            },
            'name': workout['name'],
            'instructor_id': workout['instructor_id'],
            'max_participants': workout['max_participants'],
            'date': date,
            'participants': [],
        } for workout in workouts
    ]
    db.workouts.insert_many(workouts)
    return workouts


# In[ ]:


# registration for a workout


# asking for a membership card number
@bot.message_handler(func = lambda message: message.text == MESSAGES['signup'])
def signupHandler(message):
    msg = bot.send_message(
        message.chat.id,
        'Введите номер клубной карты:'
    )
    bot.register_next_step_handler(msg, selectEnrollDay)
    
# suggests next 7 days from today to pick from
def selectEnrollDay(message):
    keyboard = telebot.types.InlineKeyboardMarkup()
    week_day = datetime.datetime.today().weekday()
    week_day = week_day + 1 if week_day < 6 else 0
    today = datetime.date.today()
    buttons = []
    
    for index, i in enumerate(list(range(week_day,7)) + list(range(0, week_day))):
        current_day = today + datetime.timedelta(days=index + 1)
        date = '{}.{}'.format(current_day.strftime("%d"), current_day.strftime("%m"))
        day_code = list(MESSAGES['weekdays'].keys())[i]
        day_name = MESSAGES['weekdays'][day_code]
        keyboard.add(
            telebot.types.InlineKeyboardButton(
                text='{} ({})'.format(
                    day_name,
                    date
                ),
                callback_data='wked|card_id,{},d,{},wd,{}'.format(message.text, date, day_code)
            )
        )

    msg = bot.send_message(
        message.chat.id,
        'Выберите удобный день: ', 
        reply_markup = keyboard,
        parse_mode = 'markdown',
    )

# suggests user to pick available (not full) workouts for a chosen day
@bot.callback_query_handler(func=lambda data: data.data.startswith('wked|'))
def selectWorkout(call):
    data = call.data.split('|')[1].split(',')
    data = list(chunks(data, 2))
    data = dict([(pair[0], pair[1]) for pair in data])

    message = call.message

    date = data['d']
    week_day = data['wd']

    workouts = [wk for wk in getWorkoutDay(week_day, date) if len(wk['participants']) < wk['max_participants']]
    
    if len(workouts) == 0:
        msg = bot.send_message(message.chat.id, 'На выбранный день запись полная')
        
        
    keyboard = telebot.types.InlineKeyboardMarkup(row_width = 1)
    
    buttons = []
    for wk in workouts:
        buttons.append(
            telebot.types.InlineKeyboardButton(
                text='{}-{} {} [{}/{}]'.format(wk['time']['from'], wk['time']['to'], wk['name'], len(wk['participants']), wk['max_participants']),
                callback_data='wk|id,{},card_id,{}'.format(wk['_id'], data['card_id'])
            )
        )
    keyboard.add(*buttons)
    msg = bot.send_message(message.chat.id, 'Выберите тренировку:', reply_markup = keyboard)


# checks whether user is already enrolled to selected workout.
# if it is, sends 'Вы уже записаны на эту тренировку'
# enrolls user and saves it to the database otherwise
@bot.callback_query_handler(func=lambda data: data.data.startswith('wk|'))
def enrollToWorkout(call):
    data = call.data.split('|')[1].split(',')
    data = list(chunks(data, 2))
    data = dict([(pair[0], pair[1]) for pair in data])    

    x = db.workouts.find_one({ '_id': ObjectId(data['id']) })
    
    if data['card_id'] in x['participants']:
        bot.send_message(
            call.message.chat.id,
            'Вы уже записаны на эту тренировку',
            reply_markup = DEFAULT_KEYBOARD,
        )
        return
    db.workouts.find_one_and_update(
        { '_id' : ObjectId(data['id']) },
        {
            '$set': {
                'participants':  x['participants'] + [data['card_id']]
            }
        }
    )

    msg = 'Вы записаны на тренировку по карте {}'.format(data['card_id'])
    workout = db.workouts.find({ 'id': data['id'] })
    bot.send_message(
        call.message.chat.id,
        msg,
        reply_markup = DEFAULT_KEYBOARD,
    )
    
    
if __name__ == '__main__':
    bot.polling(none_stop=True)


# In[ ]:




