#!/usr/bin/env ruby

require 'dotenv/load'
require 'discordrb'

DATA_DIR = 'data'
DAY_FILE = 'day.txt'.freeze

day = 1
if !File.exist?(DAY_FILE)
  File.write(DAY_FILE, day)
else
  day = Integer(File.read(DAY_FILE))
end

week = ((day - 1) / 7).floor + 1

file_prefix = "ex#{day.to_s.rjust(3, '0')}-week#{week.to_s.rjust(2, '0')}"

image_path = File.join(DATA_DIR, 'images', "#{file_prefix}.png")
audio_path = File.join(DATA_DIR, 'audio', "#{file_prefix}.mp3")

image = File.open(image_path, 'rb')
audio = File.open(audio_path, 'rb')

API_TOKEN = ENV['API_TOKEN']
puts 'API_TOKEN not set!' unless API_TOKEN

CHANNEL = ENV['CHANNEL']
puts 'CHANNEL not set!' unless CHANNEL

bot = Discordrb::Bot.new(token: API_TOKEN)

# bot.channel(CHANNEL).send_embed("Exercise #{day} week #{week}", nil, [image, audio]) do |e|
#  e.image = Discordrb::Webhooks::EmbedImage.new(url: "attachment://#{file_prefix}.png")
# end

bot.channel(CHANNEL).send_message("Exercise #{day} week #{week}", false, nil, [image, audio])

day += 1
File.write(DAY_FILE, day % 365)
