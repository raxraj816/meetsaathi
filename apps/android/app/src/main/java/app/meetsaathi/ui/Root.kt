package app.meetsaathi.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.imePadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Bookmarks
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import app.meetsaathi.R
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.meetsaathi.core.SessionState
import app.meetsaathi.core.SessionStateMachine
import app.meetsaathi.ui.components.clock
import app.meetsaathi.ui.screens.AskScreen
import app.meetsaathi.ui.screens.InsightDetailScreen
import app.meetsaathi.ui.screens.InsightsScreen
import app.meetsaathi.ui.screens.MemoryDetailScreen
import app.meetsaathi.ui.screens.ProjectScreen
import app.meetsaathi.ui.screens.ProjectsScreen
import app.meetsaathi.ui.screens.SessionsScreen
import app.meetsaathi.ui.screens.ShareScreen
import app.meetsaathi.ui.screens.AuthScreen
import app.meetsaathi.ui.screens.ContextChooserScreen
import app.meetsaathi.ui.screens.HomeScreen
import app.meetsaathi.ui.screens.InterviewScreen
import app.meetsaathi.ui.screens.LiveAskSheet
import app.meetsaathi.ui.screens.LiveScreen
import app.meetsaathi.ui.screens.MemoriesScreen
import app.meetsaathi.ui.screens.MockScreen
import app.meetsaathi.ui.screens.PreflightScreen
import app.meetsaathi.ui.screens.RecapScreen
import app.meetsaathi.ui.screens.SampleScreen
import app.meetsaathi.ui.screens.SpeakersScreen
import app.meetsaathi.ui.screens.StudyScreen
import app.meetsaathi.ui.screens.TranscriptScreen
import app.meetsaathi.ui.screens.VoiceScreen
import app.meetsaathi.ui.screens.WelcomeScreen
import app.meetsaathi.ui.screens.YouScreen
import app.meetsaathi.ui.theme.LocalMs

private val tabRoutes = setOf(Route.Home, Route.Memories, Route.Ask, Route.You)

@Composable
fun MeetSaathiRoot(vm: AppViewModel) {
    val ui by vm.ui.collectAsState()
    val live by vm.live.state.collectAsState()
    val t = LocalMs.current
    val snack = remember { SnackbarHostState() }
    LaunchedEffect(ui.toast) { ui.toast?.let { snack.showSnackbar(it); vm.toast(null) } }
    LaunchedEffect(ui.error) { ui.error?.let { snack.showSnackbar(it); vm.clearError() } }
    BackHandler(enabled = ui.back.isNotEmpty()) { vm.back() }

    val showTabs = ui.route in tabRoutes
    Scaffold(
        containerColor = t.canvas,
        snackbarHost = { SnackbarHost(snack) },
        bottomBar = {
            if (showTabs) NavigationBar(containerColor = t.surface) {
                Tab.entries.forEach { tab ->
                    NavigationBarItem(selected = ui.route == tab.route, onClick = { vm.tab(tab) },
                        // Decorative icon: the visible label is the accessible name.
                        icon = { Icon(when (tab) { Tab.Home -> Icons.Outlined.Home; Tab.Memories -> Icons.Outlined.Bookmarks
                            Tab.Ask -> Icons.Outlined.AutoAwesome; Tab.You -> Icons.Outlined.Person }, contentDescription = null) },
                        label = { Text(stringResource(tab.label)) },
                        colors = NavigationBarItemDefaults.colors(selectedTextColor = t.accent, selectedIconColor = t.accent,
                            unselectedTextColor = t.secondary, unselectedIconColor = t.secondary, indicatorColor = t.raised))
                }
            }
        },
    ) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).imePadding()) {
            // Persistent mini-bar: an active session is recoverable from every tab (master 2.1).
            val s = live.session
            if (showTabs && s != null && SessionState.parse(s.state) in SessionStateMachine.active) {
                Row(Modifier.fillMaxWidth().background(t.raised).clickable(role = Role.Button) { vm.go(Route.Live) }.padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.minibar, stringResource(live.truth.labelRes), s.title, clock(live.elapsedMs)), color = t.text, fontWeight = FontWeight.SemiBold)
                }
            }
            Box(Modifier.fillMaxSize()) {
                when (val r = ui.route) {
                    Route.Welcome -> WelcomeScreen(vm)
                    Route.Auth -> AuthScreen(vm, ui)
                    Route.Sample -> SampleScreen(vm)
                    Route.Home -> HomeScreen(vm, ui, live)
                    Route.ContextChooser -> ContextChooserScreen(vm)
                    Route.Preflight -> PreflightScreen(vm, ui, live)
                    Route.Live -> LiveScreen(vm, ui, live)
                    Route.LiveAsk -> LiveAskSheet(vm, ui, live)
                    is Route.Transcript -> TranscriptScreen(vm, ui, live, r.sessionId)
                    Route.Voice -> VoiceScreen(vm, live)
                    is Route.Recap -> RecapScreen(vm, ui, r.sessionId, live)
                    is Route.Speakers -> SpeakersScreen(vm, ui, r.sessionId)
                    is Route.MemoryDetail -> MemoryDetailScreen(vm, ui, r.claimId)
                    is Route.InsightDetail -> InsightDetailScreen(vm, ui, r.sessionId, r.insightId)
                    is Route.Insights -> InsightsScreen(vm, ui, r.sessionId)
                    is Route.Share -> ShareScreen(vm, ui, r.sessionId)
                    Route.Sessions -> SessionsScreen(vm, ui)
                    Route.Projects -> ProjectsScreen(vm, ui)
                    is Route.Project -> ProjectScreen(vm, ui, r.projectId)
                    Route.Memories -> MemoriesScreen(vm, ui)
                    Route.Ask -> AskScreen(vm, ui)
                    Route.You -> YouScreen(vm, ui)
                    Route.Study -> StudyScreen(vm, ui)
                    Route.Interview -> InterviewScreen(vm, ui)
                    is Route.Mock -> MockScreen(vm, ui, r.mockId)
                }
            }
        }
    }
}
