package app.meetsaathi

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import app.meetsaathi.ui.AppViewModel
import app.meetsaathi.ui.MeetSaathiRoot
import app.meetsaathi.ui.theme.MeetSaathiTheme

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels { AppViewModel.factory((application as MeetSaathiApp).container) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { MeetSaathiTheme { MeetSaathiRoot(vm) } }
    }
}
