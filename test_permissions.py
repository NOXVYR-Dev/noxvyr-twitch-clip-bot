"""Offline permission checks; no Discord login, Twitch calls or database access."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
from discord import app_commands

import bot as module


class CommandPermissionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_administrators_can_use_every_command(self):
        for command in module.bot.tree.get_commands():
            with self.subTest(command=command.name):
                interaction = SimpleNamespace(
                    guild_id=123, permissions=discord.Permissions(administrator=True)
                )
                self.assertTrue(await command._check_can_run(interaction))

    async def test_non_admins_cannot_use_any_command(self):
        cases = ({}, {"manage_guild": True}, {"manage_messages": True},
                 {"manage_guild": True, "manage_messages": True})
        for command in module.bot.tree.get_commands():
            for permissions in cases:
                with self.subTest(command=command.name, permissions=permissions):
                    interaction = SimpleNamespace(
                        guild_id=123, permissions=discord.Permissions(**permissions)
                    )
                    with self.assertRaises(app_commands.MissingPermissions):
                        await command._check_can_run(interaction)

    def test_discord_registration_is_admin_only_and_guild_only(self):
        commands = module.bot.tree.get_commands()
        self.assertEqual({c.name for c in commands},
                         {"clip-setup", "clip-status", "clip-remove"})
        for command in commands:
            with self.subTest(command=command.name):
                self.assertTrue(command.guild_only)
                self.assertEqual(command.default_permissions.value,
                                 discord.Permissions(administrator=True).value)

    async def test_denial_is_private_and_names_administrator_permission(self):
        for responded in (False, True):
            with self.subTest(responded=responded):
                interaction = SimpleNamespace(
                    response=SimpleNamespace(is_done=Mock(return_value=responded),
                                             send_message=AsyncMock()),
                    followup=SimpleNamespace(send=AsyncMock()),
                )
                await module.on_app_command_error(
                    interaction, app_commands.MissingPermissions(["administrator"])
                )
                sender = (interaction.followup.send if responded
                          else interaction.response.send_message)
                sender.assert_awaited_once()
                self.assertTrue(sender.call_args.kwargs["ephemeral"])
                self.assertIn("**Administrator**", sender.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
