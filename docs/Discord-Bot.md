The discord bot can send notifications about UA progress to a discord channel.
Currently, the notifications are limited too a UA process starting, which sites succeeded and which sites failed to upload, and UA process finished.

Apart from turning the bot on and off, the only other option currently is whether or not the bot should only post notifications during unattended processing. See the bottom of the `example-config` for config options.

This wiki will only give a brief overview that may help you create and setup a discord bot.
There are some (outdated) steps that can be followed at the python bot docs: https://discordpy.readthedocs.io/en/latest/discord.html

I also recommend reading the excellent Requestrr wiki: https://github.com/thomst08/requestrr/wiki/Connecting-the-bot-to-Discord

The bot token can be found on the BOT page in your discord dev overview:
The bot also requires `Message Content Intent` enabled.
I also recommend to disable the `Public Bot` option so that you have full control over what channels the bot can be added too.
![Screenshot 2025-06-11 163833](https://github.com/user-attachments/assets/fd1e6b1e-19e8-410b-ac07-6f5ac45b1825)

The discord channel id can be found by right clicking a channel and selecting `copy channel id`.

![Screenshot 2025-06-11 165249](https://github.com/user-attachments/assets/618e6303-72ef-413b-8e92-c333e68ec01a)

Example:
![Screenshot 2025-06-11 165511](https://github.com/user-attachments/assets/507fbd9e-4564-429b-a14d-188b0e32b93c)