import copy
import unittest
import core

class Policies(unittest.TestCase):
    def test_fresh_configuration_is_paused_and_has_no_external_dependency(self):
        cfg=core.defaults();core.validate(cfg)
        self.assertFalse(cfg['enabled']);self.assertEqual(core.ROLE_SPECS['rippers'][1],[])
        self.assertEqual(len(core.CLAIM_KEYS),4)
    def test_pre_entry_visibility_is_exact(self):
        public={k for k,s in core.BLUEPRINT.items() if s['kind']!='category' and core.access_policy(s)['public']['view_channel']}
        self.assertEqual(public,{'rules','verification','faq','official_links'})
        for key in public:
            self.assertTrue(core.access_policy(core.BLUEPRINT[key])['public']['read_message_history'])
            self.assertFalse(core.access_policy(core.BLUEPRINT[key])['public']['send_messages'])
    def test_ordinary_member_never_gets_management_or_privileged_hidden_channels(self):
        for key,s in core.BLUEPRINT.items():
            p=core.access_policy(s)['rippers']
            for flag in ('manage_roles','manage_channels','manage_messages','manage_threads','manage_webhooks','mention_everyone','create_private_threads','use_external_apps'):
                self.assertFalse(p[flag],(key,flag))
            if s['access'] in ('og','staff'):self.assertFalse(p['view_channel'],key)
            else:self.assertTrue(p['read_message_history'],key)
    def test_read_only_channels_have_no_thread_bypass(self):
        for key in ('rules','faq','announcements','community_news','proposals','notifications'):
            p=core.access_policy(core.BLUEPRINT[key])['rippers']
            self.assertTrue(p['read_message_history']);self.assertTrue(p['add_reactions'])
            for f in ('send_messages','send_messages_in_threads','create_public_threads','create_private_threads','attach_files','embed_links'):self.assertFalse(p[f],(key,f))
    def test_general_and_show_off_media_rules(self):
        general=core.access_policy(core.BLUEPRINT['general'])['rippers']
        self.assertTrue(general['send_messages']);self.assertTrue(general['attach_files']);self.assertTrue(general['embed_links'])
        show=core.access_policy(core.BLUEPRINT['show_off'])['rippers']
        self.assertTrue(show['attach_files']);self.assertFalse(show['embed_links'])
    def test_daily_post_cannot_be_sent_directly(self):
        p=core.access_policy(core.BLUEPRINT['gcars'])['rippers']
        self.assertFalse(p['send_messages']);self.assertFalse(p['attach_files']);self.assertFalse(p['embed_links'])
        self.assertEqual(core.BLUEPRINT['gcars']['slowmode'],86400)
        self.assertEqual(core.BLUEPRINT['content']['slowmode'],7200)
    def test_og_does_not_open_holder_or_tickets(self):
        for key in ('holder','open_tickets','closed_tickets','gate_log'):
            self.assertEqual(core.access_policy(core.BLUEPRINT[key])['og'],{})
        self.assertTrue(core.access_policy(core.BLUEPRINT['owners_chat'])['og']['view_channel'])
        self.assertTrue(core.access_policy(core.BLUEPRINT['proposals'])['rippers']['view_channel'])
    def test_staff_can_see_history_and_moderate_every_channel(self):
        for s in core.BLUEPRINT.values():
            p=core.access_policy(s)['staff']
            for f in ('view_channel','read_message_history','manage_messages','manage_threads'):self.assertTrue(p[f])
    def test_cannot_disable_every_question(self):
        cfg=core.defaults()
        for q in cfg['questions']:q['enabled']=False
        with self.assertRaises(ValueError):core.validate(cfg)
    def test_native_and_custom_cooldown_validation(self):
        cfg=core.defaults();cfg['blueprint']['general']['slowmode']=86400
        with self.assertRaises(ValueError):core.validate(cfg)
        cfg=core.defaults();cfg['blueprint']['holder']['access']='member'
        with self.assertRaises(ValueError):core.validate(cfg)
    def test_defaults_do_not_share_mutable_state(self):
        a,b=core.defaults(),core.defaults();a['questions'][0]['label']='changed'
        self.assertNotEqual(a['questions'][0]['label'],b['questions'][0]['label'])

if __name__=='__main__':unittest.main()
